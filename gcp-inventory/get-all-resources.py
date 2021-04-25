from pprint import pprint
from google.cloud import resource_manager
from google.cloud import asset_v1

# To Do: Filter For Desired Resources via asset_type

# Prints out all resources within all projects
# access is granted for
# Output : 
#    results {
#      name: "//storage.googleapis.com/{bucket name}"
#      asset_type: "storage.googleapis.com/Bucket"
#      project: "projects/{project number}"
#      display_name: "{bucket name}"
#      location: "us-east1"
#.   }
#

def get_all_resources():
    # Get Projects
    rmclient = resource_manager.Client()
    asclient = asset_v1.AssetServiceClient()
    for project in rmclient.list_projects():
        current_project = project.project_id
        # Get All Resources In Each Project
        response = asclient.search_all_resources(
            request={
                "scope": f"projects/{current_project}",
            }
        )
        pprint(response)

get_all_resources()
