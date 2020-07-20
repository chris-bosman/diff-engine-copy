import os
import json
import re

from bson import json_util
from dotenv import load_dotenv

load_dotenv()

import db
import meta

from cloud_providers import aws
from diffs.terraform import generate_diffs
from readers import terraform

#TODO: Create entry point for supplying cloud providers, credentials, tfstate, etc.
def main():
    # Register MongoDB Collections
    # TODO: Codify MongoDB instance creation w/ these DBs & Collections rather than doing this in-app
    register_aws = db.collections.register_aws_collections()
    register_tfstate = db.collections.register_terraform_collections(f"{os.getenv('AWS_S3_BUCKET')}/{os.getenv('AWS_S3_PATH')}")

    # Store Data
    # TODO: Cron this w/ exponential backoff
    # TODO: Provide iterable list of statefiles to app
    # TODO: Find way to iterate over resource types for infra
    terraform.store_tfstate_s3(os.getenv('AWS_S3_BUCKET'), os.getenv('AWS_S3_PATH'))
    aws.store_vpcs()
    aws.store_subnets()
    meta.generate_docs(os.getenv('AWS_S3_BUCKET'), os.getenv('AWS_S3_PATH'))

    # Generate diffs
    diffs = generate_diffs(os.getenv('AWS_S3_BUCKET'), os.getenv('AWS_S3_PATH'))

    # Show diffs
    output = generate_output()

def generate_output():
    diff_colls = db.mongo.diff_db.list_collection_names()

    if len(diff_colls) > 0:
        for coll in diff_colls:
            index = coll.split("-")
            resource_type = re.search(re.compile("[^-]*"), coll)[0]
            svc_pointer = coll.replace(resource_type, "")[1:len(coll)-2]

            print(f"""\n
            ##############################
            Source Control: {svc_pointer}
            Resource Type: {resource_type}
            ##############################
            \n""")

            diff_docs = db.mongo.diff_db[coll].find()

            for doc in diff_docs:
                print(json.dumps(doc['diffs'], sort_keys=True, indent=12, default=json_util.default) + "\n")

    else:
        print("No drift detected.")

if __name__ == "__main__":
    main()