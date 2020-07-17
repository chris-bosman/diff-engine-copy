import boto3
import os

from db import mongo
from pymongo import ReturnDocument

# This will fail without environment variables for authorization. This is intentional.
ec2 = boto3.client('ec2', region_name=os.getenv('AWS_REGION'))

def store_vpcs():
    vpcs = ec2.describe_vpcs()['Vpcs']
    vpc_collection = mongo.infra_db["aws_vpc"]

    for vpc in vpcs:
        vpc = supplement_vpc_data(vpc)

        vpc_collection.find_one_and_replace(
            {'VpcId': vpc['VpcId']},
            vpc,
            return_document=ReturnDocument.AFTER,
            upsert=True
        )

    return {
        "message": "Successfully uploaded documents",
        "status": 200
    }

def store_subnets():
    subnets = ec2.describe_subnets()['Subnets']
    subnet_collection = mongo.infra_db["aws_subnet"]

    for subnet in subnets:
        subnet = supplement_subnet_data(subnet)

        subnet_collection.find_one_and_replace(
            {'SubnetId': subnet['SubnetId']},
            subnet,
            return_document=ReturnDocument.AFTER,
            upsert=True
        )

    return {
        "message": "Success",
        "status": 200
    }

def supplement_vpc_data(vpc):
    classic_link = ec2.describe_vpc_classic_link(VpcIds=[vpc['VpcId']])
    classic_link_dns = ec2.describe_vpc_classic_link_dns_support(VpcIds=[vpc['VpcId']])
    dns_support = ec2.describe_vpc_attribute(Attribute='enableDnsSupport', VpcId=vpc['VpcId'])
    dns_hostnames = ec2.describe_vpc_attribute(Attribute='enableDnsHostnames', VpcId=vpc['VpcId'])
    enable_classiclink = classic_link['Vpcs'][0]['ClassicLinkEnabled']
    enable_classiclink_dns_support = classic_link_dns['Vpcs'][0]['ClassicLinkDnsSupported']
    enable_dns_support = dns_support['EnableDnsSupport']['Value']
    enable_dns_hostnames = dns_hostnames['EnableDnsHostnames']['Value']

    supplemental_vpc_data = {
        "EnableClassicLink": enable_classiclink,
        "EnableClassicLinkDnsSupport": enable_classiclink_dns_support,
        "EnableDnsSupport": enable_dns_support,
        "EnableDnsHostnames": enable_dns_hostnames
    }

    for field in supplemental_vpc_data.keys():
        vpc[field] = supplemental_vpc_data[field]

    if "Ipv6CidrBlockAssociationSet" in vpc.keys():
        if vpc["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlockState"]["State"] == "associated":
            vpc["AssignIpv6Block"] = True
    else:
        vpc["AssignIpv6Block"] = False

    return vpc

def supplement_subnet_data(subnet):
    if subnet["Ipv6CidrBlockAssociationSet"] == []:
        subnet["Ipv6CidrBlock"] = ""
    else:
        print(subnet["Ipv6CidrBlockAssociationSet"])
        subnet["Ipv6CidrBlock"] = subnet["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlock"]

    if "OutpostArn" not in subnet.keys():
        subnet["OutpostArn"] = ""
    
    return subnet
