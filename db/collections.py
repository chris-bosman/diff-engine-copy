from db import mongo
from pymongo.errors import CollectionInvalid

infra_db = mongo.infra_db
svc_db = mongo.svc_db

def register_aws_collections():
    svc_collections = svc_db.list_collection_names()
    aws_collections = []
    for collection in svc_collections:
        resource_types = svc_db[collection].distinct("terraform_type")
        for resource in resource_types:
            aws_collections.append(resource)

    for collection in aws_collections:
        try:
            infra_db.create_collection(collection)
        except CollectionInvalid:
            continue
        except:
            raise ConnectionError(f"Unable to create new collection `{collection}`")

def register_terraform_collections(state_file):
    try:
        svc_db.create_collection(state_file)
    except CollectionInvalid:
        pass
    except:
        raise ConnectionError(f"Unable to create new collection `{state_file}`")