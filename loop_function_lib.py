import time
import pytz
from datetime import datetime
from pymongo import MongoClient, UpdateMany
import os

my_secret3 = os.environ['MONGO_DB_CONNECTION']

client = MongoClient(my_secret3)

db = client['test_line_bot_database']  #3 Mongodb not test version
messages_collection = db['messages']
master_users_collection = db['master_users']
image_gen_records_collection = db['image_gen_records_collection']
model_master_collection = db["model_master"]
lora_and_emb_master_collection = db["lora_and_emb_master"]
pure_message_gpt_collection = db["pure_message_gpt"]
history_pure_message_gpt_collection = db["history_pure_message_gpt"]
payment_collection = db["payment"]
credit_refill_collection = db["credit_refill"]


timezone = pytz.timezone("Asia/Bangkok")


def loop_function():
    while True:
      # Get the current time in Thailand timezone
      current_time = datetime.now(timezone)

      # Format the timestamp as a string
      timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')

      if current_time.day == 1 and current_time.hour == 0 and current_time.minute == 1 :
        print(timestamp + "It is the first day of the month at 00:01. Ready to refill token!")
        x = 25000
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
        # Calculate the remaining seconds until the next hour
        remaining_seconds =  3600 - (current_time.minute * 60 + current_time.second)
        time.sleep(remaining_seconds)

      else:
        # Calculate the remaining seconds until the next hour
        print(timestamp + "still not refill date")
        remaining_seconds =  3600 - (current_time.minute * 60 + current_time.second)
        time.sleep(remaining_seconds)