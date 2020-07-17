import os
import urllib.parse

from pymongo import MongoClient

username = urllib.parse.quote_plus(os.getenv('MONGO_USERNAME'))
password = urllib.parse.quote_plus(os.getenv('MONGO_PASSWORD'))

client = MongoClient(f"mongodb://{username}:{password}@{os.getenv('MONGO_URL')}:{os.getenv('MONGO_PORT')}")

infra_db = client['infrastructure']
svc_db = client['source-control']
meta_db = client['meta']