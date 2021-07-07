
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from dateutil import tz
import boto3
import csv
import json
import os
import time
from time import sleep

from antiope.aws_account import *
from antiope.aws_organization import *
from common import *

import logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', default='INFO')))
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


#
# Create individual csv reports of all macie findings in each account
#

CSV_HEADER = ['AccountId', 'BucketName', 'Region', 'FileExtension', 'Severity', 'FindingType',
              'FindingCount', 'Details', 'ObjectKey', 'S3Path', 'URLPath', 'FindingConsoleURL',
              'Created', 'Updated']

def lambda_handler(event, context):
    logger.debug("Received event: " + json.dumps(event, sort_keys=True))
    message = json.loads(event['Records'][0]['Sns']['Message'])
    logger.info("Received message: " + json.dumps(message, sort_keys=True))

    try:
        # We need to get the target account, then instantiate the Organization account to get the macie2
        # delegated admin
        target_account = AWSAccount(message['account_id'])
        payer_account = AWSOrganizationMaster(target_account.payer_id)
        delegated_account = payer_account.get_delegated_admin_account_for_service('macie')

        if delegated_account is None:
            logger.warning(f"Unable to find macie delegated_account for {target_account.account_id}")
            return(event)

        filename = f"/tmp/{target_account.account_id}-Findings.csv"

        findingCriteria = {'criterion': {
                                 'category':  {'eq': ['CLASSIFICATION']},
                                 'accountId': {'eq': [target_account.account_id]}
                                }
                            }

        with open(filename, 'w') as csvoutfile:
            writer = csv.writer(csvoutfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)
            writer.writerow(CSV_HEADER)

            for r in target_account.get_regions():

                # Lets get the findings from the Delegated Admin Account
                # macie_client = delegated_account.get_client('macie2', region=r)
                # FIXME, Macie doesn't always run in here, but I need my bigger creds
                macie_client = boto3.client('macie2', region_name=r)

                # Macie is annyoing in that I have to list each findings, then pass the list of ids to the
                # get_findings() API to get any useful details. Bah
                list_response = macie_client.list_findings(
                    findingCriteria=findingCriteria,
                    maxResults=50
                )
                findings = list_response['findingIds']
                logger.debug(f"Found {len(findings)} findings in {r}")
                if len(findings) == 0:
                    # No findings in this region, move along
                    continue

                # Now get the meat of  these findings
                get_response = macie_client.get_findings(findingIds=findings)
                for f in get_response['findings']:
                    bucket_name = f['resourcesAffected']['s3Bucket']['name']
                    key = f['resourcesAffected']['s3Object']['key']
                    summary, count = get_summary(f)
                    writer.writerow([f['accountId'], bucket_name, r,
                                    f['resourcesAffected']['s3Object']['extension'],
                                    f['severity']['description'], f['type'],
                                    count, summary, key,
                                    f"s3://{bucket_name}/{key}",
                                    f"https://{bucket_name}.s3.amazonaws.com/{key}",
                                    f"https://{r}.console.aws.amazon.com/macie/home?region={r}#findings?search=resourcesAffected.s3Bucket.name%3D{bucket_name}&macros=current&itemId={f['id']}",
                                    f['createdAt'], f['updatedAt']])

                # pagination is a pita. Here we continue to the List pagination
                while 'nextToken' in list_response:
                    sleep(1)
                    list_response = macie_client.list_findings(
                        findingCriteria=findingCriteria,
                        maxResults=50,
                        nextToken=list_response['nextToken']
                    )
                    findings = list_response['findingIds']
                    logger.debug(f"Found {len(findings)} more findings in {r}")
                    get_response = macie_client.get_findings(findingIds=findings)
                    for f in get_response['findings']:
                        bucket_name = f['resourcesAffected']['s3Bucket']['name']
                        key = f['resourcesAffected']['s3Object']['key']
                        summary, count = get_summary(f)
                        writer.writerow([f['accountId'], bucket_name, r,
                                        f['resourcesAffected']['s3Object']['extension'],
                                        f['severity']['description'], f['type'],
                                        count, summary, key,
                                        f"s3://{bucket_name}/{key}",
                                        f"https://{bucket_name}.s3.amazonaws.com/{key}",
                                        f"https://{r}.console.aws.amazon.com/macie/home?region={r}#findings?search=resourcesAffected.s3Bucket.name%3D{bucket_name}&macros=current&itemId={f['id']}",
                                        f['createdAt'], f['updatedAt']])

        csvoutfile.close()

        # Now save the CSV File to S3
        save_report_to_s3(message, filename, target_account.account_id)
        return(event)


    except AntiopeAssumeRoleError as e:
        logger.error("Unable to assume role into account {}({})".format(target_account.account_name, target_account.account_id))
        return()
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.debug(f"Account {target_account.account_name} ({target_account.account_id}) is not subscribed to Shield Advanced")
            return(event)
        if e.response['Error']['Code'] == 'UnauthorizedOperation':
            logger.error("Antiope doesn't have proper permissions to this account")
            return(event)
        logger.critical("AWS Error getting info for {}: {}".format(message['account_id'], e))
        capture_error(message, context, e, "ClientError for {}: {}".format(message['account_id'], e))
        raise
    except Exception as e:
        logger.critical("{}\nMessage: {}\nContext: {}".format(e, message, vars(context)))
        capture_error(message, context, e, "General Exception for {}: {}".format(message['account_id'], e))
        raise

def save_report_to_s3(event, tmp_csv, account_id):
    client   = boto3.client('s3')

    # We save two copies so we always have an easy to find point-in-time copy

    csvfile  = open(tmp_csv, 'rb')
    response = client.put_object(
        Body=csvfile,
        Bucket=os.environ['INVENTORY_BUCKET'],
        ContentType='text/csv',
        Key=f"MacieReports/{event['timestamp']}/{account_id}.csv",
    )
    csvfile.seek(0)

    response = client.put_object(
        # ACL='public-read',
        Body=csvfile,
        Bucket=os.environ['INVENTORY_BUCKET'],
        ContentType='text/csv',
        Key=f"MacieReports/latest/{account_id}.csv",
    )
    csvfile.close()


def get_summary(finding):
    summary = []
    count = 0
    for data_type in finding['classificationDetails']['result']['sensitiveData']:
        summary.append(f"{data_type['category']}: {data_type['totalCount']}")
        count += data_type['totalCount']
    return("\n".join(summary), count)

