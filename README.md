# grocery-receipt-textract

Reads and extracts data from Finnish grocery store receipts. 

## Deploy with Cloudformation
```
git clone https://github.com/markymarkus/grocery-receipt-textract.git
cd grocery-receipt-textract
aws cloudformation package --s3-bucket #REPLACE-WITH-CF-STAGE-BUCKET-NAME# --output-template-file packaged.yaml --region eu-west-1 --template-file template.yml
aws cloudformation deploy --template-file packaged.yaml --stack-name dev-grocery-pipeline --parameter-overrides InputBucketName=my-grocery-tracking-bucket --capabilities CAPABILITY_IAM

# After the stack finishes, two buckets for receipts and pipeline outputs are created:
# Input = my-grocery-tracking-bucket
# Output = my-grocery-tracking-bucket-output
```

## Test with the receipts
```
aws s3 sync test_data s3://my-grocery-tracking-bucket/

# Wait for about 1 min and check the results from the output bucket. Each bucket contains one receipt json:
aws s3 ls s3://my-grocery-tracking-bucket-output/
#PRE store=K-Market Domus/
#PRE store=S-MARKET KALEVA PUH 0107671180/
```