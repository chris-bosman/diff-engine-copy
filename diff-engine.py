import os
import json

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
    print(f"\nGenearting diffs in environment `staging`:\n")
    diffs = generate_diffs(os.getenv('AWS_S3_BUCKET'), os.getenv('AWS_S3_PATH'))

    print(diffs)

if __name__ == "__main__":
    main()