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

        check_existing = meta_collection.find_one({
            "diff_ids": to_diff
        })

        if check_existing == None:
            meta_collection.find_one_and_replace(
                {"diff_ids": "$exists"},
                {"diff_ids": to_diff},
                return_document=ReturnDocument.AFTER,
                upsert=True
            )
        
def document_tf_vpcs(bucket, key):
    state_collection = mongo.svc_db[f"{bucket}/{key}"]
    infra_vpc_collection = mongo.infra_db["aws_vpcs"]
    
    tf_cursor = state_collection.find({
        "terraform_type": "aws_vpc"
    })

    infra_cursor = infra_vpc_collection.find({})

    tf_vpcs = [ vpc for vpc in tf_cursor ]
    infra_vpcs = [ vpc for vpc in infra_cursor ]

    vpcs_to_diff = []
    for tfvpc in tf_vpcs:
        for awsvpc in infra_vpcs:
            if tfvpc['aws_id'] == awsvpc['VpcId'] and tfvpc['aws_id'] not in vpcs_to_diff:
                vpcs_to_diff.append(awsvpc['VpcId'])

    collection = mongo.meta_db[f"aws_vpcs-{bucket}/{key}"]

    check_existing = collection.find_one({
        "diff_vpc_ids": vpcs_to_diff
    })

    if check_existing != None:
        collection.find_one_and_replace(
            { "diff_vpc_ids": "$exists" },
            {
                "diff_vpc_ids": vpcs_to_diff
            },
            return_document=ReturnDocument.AFTER,
            upsert=True
        )