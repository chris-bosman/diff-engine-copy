from db import mongo
from pymongo import ReturnDocument

def document_tf_resources(bucket, key):
    state_collection = mongo.svc_db[f"{bucket}/{key}"]
    infra_collections = mongo.infra_db.list_collection_names()

    for collection in infra_collections:
        tf_cursor = state_collection.find({
            "terraform_type": collection
        })

        infra_cursor = mongo.infra_db[collection].find({})

        tf_resources = [ resource for resource in tf_cursor ]
        infra_resources = [ resource for resource in infra_cursor ]

        to_diff = []
        for resource in tf_resources:
            for infra in infra_resources:
                if resource['aws_id'] in infra.values() and resource['aws_id'] not in to_diff:
                    to_diff.append(resource['aws_id'])

        meta_collection = mongo.meta_db[f"{collection}-{bucket}/{key}"]
        meta_collection.delete_many({})
        meta_collection.find_one_and_replace(
            {"diff_ids": "$exists"},
            {"diff_ids": to_diff},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )