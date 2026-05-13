terraform {
  backend "gcs" {
    bucket = "testlyn-tfstate"
    prefix = "dev/"
  }
}
