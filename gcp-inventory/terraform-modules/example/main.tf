module "antiope" {
  source          = "../"
  organization    = var.organization
  env             = var.env
  code_location   = var.code_location
}