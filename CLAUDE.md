# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Antiope is an open-source AWS inventory and compliance framework that collects resource data across hundreds of AWS accounts from a centralized Security Account. It uses cross-account roles to gather inventory and stores data in S3.

This is the **main Antiope repository** containing core inventory functionality. It is designed to be used as a git submodule within a private customization repository (antiope-local) that contains organization-specific config and Lambda functions.

## Architecture

### Modular Stack Design

Antiope consists of a main CloudFormation stack:

**AWS Inventory Stack** (`aws-inventory/cloudformation/Inventory-Template.yaml`):
- Step Functions orchestrating inventory collection
- Lambda functions for each AWS service (EC2, S3, IAM, VPC, etc.)
- DynamoDB tables for account and billing data
- SNS topics for triggering inventory across accounts

**Note:** Earlier versions of Antiope included Cognito and Elasticsearch stacks for authentication and search capabilities. These have been removed to simplify the architecture and allow organizations to use their own search and authentication solutions.

### Data Model

All resources follow a standardized format based on AWS Config Service:

**Required fields:**
- `awsAccountId` - Account ID where resource exists
- `awsAccountName` - Account name from DynamoDB
- `resourceType` - Uses AWS Config/CloudFormation naming (e.g., "AWS::EC2::Instance")
- `resourceId` - Globally unique identifier (may include account/region)
- `source` - Always "Antiope"
- `configurationItemCaptureTime` - Timestamp of collection
- `configuration` - Result of the primary describe/list API call
- `supplementaryConfiguration` - Additional API calls for related data
- `errors` - Dict of any errors encountered during collection

**Optional fields:**
- `awsRegion` - Region (omitted for global services)
- `tags` - Normalized dict of tags
- `resourceName` - Name from tag or describe call
- `ARN` - Amazon Resource Name
- `resourceCreationTime` - Creation timestamp

### Storage Structure in S3

```
s3://bucket/
  Resources/<service>/<type>/<resourceId>.json    # All inventory objects
  Reports/                                         # Generated reports (CSV/HTML)
  CredentialReports/                               # IAM credential reports
  Health/                                          # Personal Health Events
  PublicIPs/                                       # Public IP inventory
  deploy-packages/                                 # Lambda zips and CFT templates
  config-files/                                    # Antiope configuration
```

### Integration Points

**SNS Topics for Custom Functions:**
- `TriggerAccountInventoryFunctionTopic` - Publishes message for each account during inventory
- `TriggerPayerInventoryFunctionTopic` - Publishes message for payer accounts only
- `NewAccountNotificationTopic` - Publishes when new account discovered
- `ForeignAccountNotificationTopic` - Publishes when trusted external account discovered

**Custom Step Functions:**
- Main Antiope Step Function can invoke a custom Step Function after inventory completes
- Pass ARN via `pDeployCustomStackStateMachineArn` parameter

## Common Commands

**Note:** Commands in this directory require `BUCKET`, `MAIN_STACK_NAME`, and `DEPLOY_PREFIX` environment variables. These are typically sourced from `config.$env` in the parent antiope-local repo.

### Testing and Validation

```bash
# Test Python syntax across all lambda functions
make test

# Run PEP8 style checks
make pep8

# Validate CloudFormation templates
make cft-validate
```

### Build and Package

```bash
# Build Lambda Layer with dependencies
make layer

# Install dependencies into lambda directories
make deps

# Clean build artifacts
make clean
```

### Development Workflow for Lambda Functions

From `aws-inventory/` directory:

```bash
# Package lambda code and dependencies
make package

# Update all Lambda function code without CloudFormation deploy
make update

# Update a single function quickly during development
make fupdate function=<STACK_PREFIX>-aws-inventory-<service>-inventory
```

### Operational Commands

From `aws-inventory/` directory:

```bash
# Set CloudWatch log retention to 5 days (default is indefinite)
make expire-logs

# Purge DynamoDB tables (dangerous!)
make purge-tables

# Delete all Lambda CloudWatch log groups
make purge-logs
```

## Adding New Inventory Resources

Follow this process to add a new AWS service inventory:

### 1. Create Lambda Function

- Filename: `aws-inventory/lambda/inventory-<service>.py`
- Use resource types from AWS Config or CloudFormation conventions
- Import `from antiope.aws_account import AWSAccount`
- Use helper functions: `parse_tags()`, `save_resource_to_s3()`
- Store in `Resources/<service>/<type>/<resourceId>.json`

**Key considerations:**
- Check if API calls require pagination
- Determine if resource is regional or global (don't iterate regions for global services)
- Ensure `resourceId` is globally unique (include account/region if needed)
- Handle errors gracefully - add to `errors` dict, don't fail entire inventory

### 2. Update CloudFormation Template

Add function to `aws-inventory/cloudformation/Inventory-Template.yaml`:

```yaml
MyServiceInventoryLambdaFunction:
  Type: AWS::Serverless::Function
  Properties:
    FunctionName: !Sub "${pResourcePrefix}-myservice-inventory"
    Description: Inventory MyService Resources
    Handler: inventory-myservice.lambda_handler
    Role: !GetAtt InventoryLambdaRole.Arn
    CodeUri: ../lambda
    Events:
      AccountInventoryTrigger:
        Type: SNS
        Properties:
          Topic: !Ref TriggerAccountInventoryFunctionTopic
```

Subscribe to `TriggerPayerInventoryFunctionTopic` if only for payer accounts.

Add to dashboard sections (3 locations with different periods: 604800, 604800, 900):
```yaml
[ "...", "${AWS::StackName}-myservice-inventory", { "stat": "Sum", "period": 604800 } ]
```

### 3. Update Makefiles

In `aws-inventory/lambda/Makefile`, add to `FILES=` list:
```makefile
inventory-myservice.py \
```

In `aws-inventory/Makefile`, add to `FUNCTIONS=` list:
```makefile
$(RESOURCE_PREFIX)-myservice-inventory \
```

### 4. Deploy

```bash
# First deployment (uploads code and updates CloudFormation)
make deploy env=<envname>

# Quick updates during development (single function)
cd aws-inventory
make fupdate function=<STACK_PREFIX>-aws-inventory-myservice-inventory

# Update dependencies and all functions
cd aws-inventory
make update
```

## Python Development

### antiope-aws-module Library

The `antiope` Python package (from `antiope-aws-module` submodule) provides key classes:

**AWSAccount class** (`antiope.aws_account.AWSAccount`):
- Represents an AWS account with DynamoDB lookup
- Methods:
  - `get_creds()` - Assume cross-account role, returns credentials dict
  - `get_client(service, region)` - Get boto3 client with assumed role
  - `get_resource(service, region)` - Get boto3 resource with assumed role
  - `get_regions(service)` - Get list of regions for a service
- Attributes: `account_id`, `account_name`, `payer_id`, `root_email`, etc.

**AntiopeConfig class** (`antiope.config.AntiopeConfig`):
- Loads configuration from environment variables
- Provides DynamoDB table references, S3 bucket, role names

**Utility functions** in `aws-inventory/lambda/common.py`:
- `parse_tags(tagset)` - Convert AWS tag list to dict
- `save_resource_to_s3(prefix, resource_id, resource)` - Save JSON to S3

View full documentation:
```bash
cd antiope-aws-module
pydoc antiope.aws_account
pydoc antiope.config
```

### Lambda Dependencies

Dependencies are managed via:
1. **Lambda Layer** (`lambda_layer/`) - Shared libraries (boto3, botocore, etc.)
2. **requirements.txt** in lambda directories - Function-specific packages
3. **antiope-aws-module** - Copied into lambda package during `make deps`

The `make deps` command installs requirements.txt and the antiope module into the lambda directory.

## CloudFormation Templates

Main templates in `cloudformation/`:
- `antiope-Template.yaml` - Top-level stack orchestrating nested stacks
- `antiope-bucket-Template.yaml` - S3 bucket with proper permissions
- `SplunkHEC-Template.yaml` - Optional Splunk integration

Nested stack templates:
- `aws-inventory/cloudformation/Inventory-Template.yaml` - All inventory lambdas and Step Functions

## Customization Guidelines

**DO NOT** add proprietary/enterprise code directly to this repo. This is open-source.

**DO** use the antiope-local wrapper repo pattern for:
- Organization-specific inventory functions
- Custom reports
- Proprietary configurations

**Integration approach:**
1. Subscribe custom Lambdas to SNS topics (TriggerAccountInventoryFunctionTopic, etc.)
2. Create custom Step Function invoked after main Antiope Step Function
3. Deploy custom stack separately using cft-deploy manifests that import Antiope stack outputs

See `docs/Customizations.md` for detailed integration instructions.

## Resource Types

Antiope inventories 40+ AWS services. Common resource types:
- EC2: Instance, SecurityGroup, Volume, Snapshot, AMI, VPC, ENI, TransitGateway
- IAM: User, Role, Group (Note: IAM resources include account_id in resourceId)
- S3: Bucket (uses "bucket" prefix as resourceId)
- Compute: Lambda function, ECS cluster, ECS service
- Networking: VPC, Route53 hosted zone, Route53 domain, CloudFront distribution
- Security: GuardDuty detector, AccessAnalyzer analyzer, IAM AccessAnalyzer findings
- And many more...

See `docs/resource_types.md` for complete list.

## Important Notes

- **Antiope branch:** Typically deployed from `antiope-2.0` branch
- **Cross-account roles:** Must deploy `docs/cloudformation/SecurityCrossAccountRoleTemplate.yaml` to all accounts
- **Bucket region:** S3 bucket must be in same region as Antiope deployment
- **DynamoDB tables:** Store account metadata, populated by `pull-organization-data` Lambda
- **Step Function execution:** Triggered by CloudWatch Event (schedule) or manual invocation
- **Lambda memory:** Default 128MB, use CloudFormation params for larger functions
- **Removed components:** Cognito and Elasticsearch stacks have been removed - use your own authentication and search solutions
