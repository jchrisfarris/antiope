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

SAML_RESOURCE_PATH = "iam/saml"


def lambda_handler(event, context):
    logger.debug("Received event: " + json.dumps(event, sort_keys=True))
    message = json.loads(event['Records'][0]['Sns']['Message'])
    logger.info("Received message: " + json.dumps(message, sort_keys=True))

    try:
        target_account = AWSAccount(message['account_id'])
        discover_saml_provider(target_account)

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


def discover_saml_provider(account):
    '''
        Queries AWS to determine SAML Providers exist (and who you're trusting)
    '''
    iam_client = account.get_client('iam')
    response = iam_client.list_saml_providers()

    resource_item = {}
    resource_item['awsAccountId']                   = account.account_id
    resource_item['awsAccountName']                 = account.account_name
    resource_item['resourceType']                   = "AWS::IAM::SAML"
    resource_item['source']                         = "Antiope"

    for idp in response['SAMLProviderList']:

        # The Metadata doc (with the useful deets) are in an XML doc that requires another call
        saml = iam_client.get_saml_provider(SAMLProviderArn=idp['Arn'])
        metadata_xml = parseString(saml['SAMLMetadataDocument'])
        idp['SAMLMetadataDocument'] = metadata_xml.toprettyxml()

        # We get the name from the end of the arn
        name = idp['Arn'].split("/")[-1]

        resource_item['configurationItemCaptureTime']   = str(datetime.datetime.now())
        resource_item['configuration']                  = idp
        resource_item['supplementaryConfiguration']     = {}
        resource_item['resourceId']                     = f"{name}-{account.account_id}"
        resource_item['resourceName']                   = name
        resource_item['ARN']                            = idp['Arn']
        resource_item['resourceCreationTime']           = idp['CreateDate']
        resource_item['errors']                         = {}

        response = iam_client.list_saml_provider_tags(RoleName=idp['Arn'])
        tags = parse_tags(response['Tags'])
        if tags is not None and len(tags) != 0:
            resource_item['errors']['no_tags'] = True
        else:
            resource_item['tags'] = tags

        save_resource_to_s3(SAML_RESOURCE_PATH, resource_item['resourceId'], resource_item)

