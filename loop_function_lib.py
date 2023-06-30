import time
import pytz
from datetime import datetime
from pymongo import MongoClient, UpdateMany
import os

my_secret3 = os.environ['MONGO_DB_CONNECTION']
my_secret8 = os.environ['bucket_name']
my_secret9 = os.environ['aws_secret_access_key']

timezone = pytz.timezone("Asia/Bangkok")
# Get the current time in Thailand timezone
current_time = datetime.now(timezone)

# Format the timestamp as a string
timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')

def loop_function():
    while True:
      print(timestamp)

      if current_time.day == 1:
        x = 25000
        print("Today is 1 refill free token.")
        # Continue with the next process
        filter_criteria = {}
        update_operation = {
        '$set': {
        'freetoken': x
          }
        }
        # Create an UpdateMany object
        update_many = UpdateMany(filter_criteria, update_operation)
        # Execute the update operation
        result = master_users_collection.bulk_write([update_many])

      time.sleep(24 * 60 * 60)