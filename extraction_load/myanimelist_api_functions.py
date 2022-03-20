import requests
import json
import pandas as pd
from itertools import count
from datetime import datetime
import psycopg2

"""
A collection of functions used to gather anime 
statistics from My Anime List using the 
Jikkan API
"""


def get_page_count(url:str,session:requests.Session):
    """
    Gets the total page count 
    for the all anime endpoint
    """
    initial_response = session.get(url)
    total_pages = json.loads(initial_response.text)['pagination']['last_visible_page']
    return total_pages


def generate_anime_list(session:requests.Session,page_count:int=0):
    """
    Returns a generator containing pages from the all anime list
    """
    for page_num in range(1,page_count+1):
        url = f"https://api.jikan.moe/v4/anime?page={page_num}&sfw=true"
        resp = session.get(url)
        if resp.status_code == 200:
            yield json.loads(resp.text)
            time.sleep(1) # Space out requests to avoid errors
        else:
            print(f"Error received: {resp.status_code}")


def add_anime(anime_list,connection):
    """
    Takes in a generator of pages from the 
    generate_anime_list function and a connection,
    and adds any new titles to the database
    """
    cur = connection.cursor()
    for page in anime_list:
        for anime in page['data']:
            try:
                #Insert into database
                q = """
                    INSERT INTO anime_stage.all_anime
                    (id,title,status,rating,score
                    ,favorites,load_date,airing
                    ,aired_from,aired_to)
                    VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """ 
                cur.execute(q,(
                    anime['mal_id'],
                    anime['title'],
                    anime['status'],
                    anime['rating'],
                    anime['score'],
                    anime['favorites'],
                    datetime.now(),
                    anime['airing'],
                    anime['aired']['from'],
                    anime['aired']['to'],  
                ))
            except:
                print("Error with database connection")
                raise
    cur.close()


def get_anime_stats(session:requests.Session,anime_id:int):
    """
    Returns the stats for the anime
    associated with the given anime_id
    """
    url = f"https://api.jikan.moe/v4/anime/{anime_id}/statistics"
    resp = session.get(url)
    if resp.status_code == 200:
        return json.loads(resp.text)


def get_anime_ids(connection:psycopg2.connect):
    """
    Takes in a db connection and returns
    a DataFrame of anime ids
    """
    q = """
        SELECT id
        FROM anime.all_anime
        GROUP BY id
    """
    ids = pd.read_sql(q,connection)
    return ids


def upload_anime_stats(anime_id_list:pd.DataFrame,
                    connection:psycopg2.connect,
                    session:requests.Session):
    """
    Adds the anime stats for each id 
    in the given anime_id_list
    """
    cur = connection.cursor()
    # Setup row counter to perform a commit at every 1000 rows
    row = count(1)
    for id in anime_id_list['id']:
        # Get the stats
        stats = get_anime_stats(session,id)
        rows = next(row)
        if stats is not None and rows in range(1,1001):
            try:
                insert_stats_scores = """
                    INSERT INTO 
                        anime_stage.anime_stats_scores
                        (anime_id,scores,load_date) 
                    VALUES 
                        (%s,%s,%s)
                """
                cur.execute(insert_stats_scores,
                            (id,
                             json.dumps(stats['data']),
                             datetime.now()),
                           )
            except:
                print("Something happened with the connection.")
                print("Please check and try again")
                raise
        else:
            # Perform commit and reset counter
            connection.commit()
            row = count(1)
    cur.close()


def clear_staging(connection:psycopg2.connect):
    """
    Clears the anime_stage tables.
    """
    cursor = connection.cursor()
    cursor.execute("""
        TRUNCATE TABLE anime_stage.all_anime;
    """)
    cursor.close()


def refresh_views(connection:psycopg2.connect):
    """
    Refreshes materialized views
    """
    cursor = connection.cursor()
    cursor.execute("""
        REFRESH MATERIALIZED VIEW anime.anime_stats_and_scores;
    """)
    cursor.close()


def insert_anime_scores_and_stats(connection:psycopg2.connect):
    """
    Inserts anime scores and stats into production
    from staging
    """
    cursor = connection.cursor()
    cursor.execute("""
        SELECT anime_stage.insert_anime_stats();
        SELECT anime_stage.insert_anime_scores();
    """)
    cursor.close()