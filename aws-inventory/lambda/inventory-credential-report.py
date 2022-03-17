# Copyright 2019-2020 Turner Broadcasting Inc. / WarnerMedia
# Copyright 2021 Chris Farris <chrisf@primeharbor.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import boto3
from botocore.exceptions import ClientError
import json
import os
import time
from datetime import datetime, timezone
from dateutil import tz
import re
from xml.dom.minidom import parseString

from antiope.aws_account import *
from common import *

import logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', default='INFO')))
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


def lambda_handler(event, context):
    logger.debug("Received event: " + json.dumps(event, sort_keys=True))
    message = json.loads(event['Records'][0]['Sns']['Message'])
    logger.info("Received message: " + json.dumps(message, sort_keys=True))

    try:
        target_account = AWSAccount(message['account_id'])
        fetch_credential_report(target_account, message)

    except AntiopeAssumeRoleError as e:
        logger.error("Unable to assume role into account {}({})".format(target_account.account_name, target_account.account_id))
        return()
    except ClientError as e:
        logger.critical("AWS Error getting info for {}: {}".format(message['account_id'], e))
        capture_error(message, context, e, "ClientError for {}: {}".format(message['account_id'], e))
        raise
    except Exception as e:
        logger.critical("{}\nMessage: {}\nContext: {}".format(e, message, vars(context)))
        capture_error(message, context, e, "General Exception for {}: {}".format(message['account_id'], e))
        raise


def fetch_credential_report(account, event):
    '''
        Fetches the IAM User Credential Report and saves it to S3
    '''
    iam_client = account.get_client('iam')
    csv_data = get_credential_report(iam_client)
    object_key = f"CredentialReports/{account.account_id}-{event['timestamp']}.csv"

    s3_client = boto3.client('s3')
    try:
        response = s3_client.put_object(
            # ACL='public-read',
            Body=csv_data,
            Bucket=os.environ['INVENTORY_BUCKET'],
            ContentType='text/csv',
            Key=object_key,
        )
    except ClientError as e:
        logger.error("ClientError saving report: {}".format(e))
        raise


def get_credential_report(iam_client):
    '''Fetches the credential report. Uses recursion in case the report isn't available immediatly'''

    # Lets see if a report is already available
    try:
        response = iam_client.get_credential_report()
        credential_report_csv = response['Content'].decode('ascii')
        return(credential_report_csv)
    except ClientError as e:
        if e.response['Error']['Code'] == "ReportNotPresent":
            pass
        elif e.response['Error']['Code'] == "ReportInProgress":
            time.sleep(2)
            return get_credential_report(iam_client)
        else:
            raise  # Whatever happened here we didn't expect

    try:
        # No report - go request one get generated
        resp1 = iam_client.generate_credential_report()
        if resp1['State'] == 'COMPLETE':
            try:
                response = iam_client.get_credential_report()
                credential_report_csv = response['Content'].decode('ascii')
                # # print(credential_report_csv)
                # reader = csv.DictReader(credential_report_csv.splitlines())
                # # print(reader)
                # # print(reader.fieldnames)
                # credential_report = []
                # for row in reader:
                #     credential_report.append(row)
                return(credential_report_csv)
            except ClientError as e:
                print("Unknown error getting Report: " + e.message)
        else:
            time.sleep(2)
            return get_credential_report(iam_client)
    except ClientError as e:
        if e.response['Error']['Code'] == "Throttling":
            time.sleep(2)
            return get_credential_report(iam_client)
        else:
            raise

