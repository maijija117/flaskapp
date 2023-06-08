from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from pymongo import MongoClient
from datetime import datetime
import json
import pytz
import os
import requests

# StableDiffAPI Url
urlstdapi = "https://stablediffusionapi.com/api/v3/text2img"

# Set the timezone to Thailand
timezone = pytz.timezone("Asia/Bangkok")

my_secret = os.environ['LINE_ACCESS_TOKEN']
my_secret2 = os.environ['LINE_SECRET']
my_secret3 = os.environ['MONGO_DB_CONNECTION']
my_secret4 = os.environ['STD_API_KEY']

app = Flask(__name__)

line_bot_api = LineBotApi(my_secret)
handler = WebhookHandler(my_secret2)

# Connect to MongoDB Atlas
client = MongoClient(my_secret3)

# Specify the database and collection
db = client['line_bot_database']
messages_collection = db['messages']
master_users_collection = db['master_users']
image_gen_records_collection = db['image_gen_records_collection']

# Get the current time in Thailand timezone
current_time = datetime.now(timezone)

# Format the timestamp as a string
timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')


@app.route("/callback", methods=["POST"])
def callback():
  # Handle the webhook event with the provided signature and body
  signature = request.headers["X-Line-Signature"]
  body = request.get_data(as_text=True)

  try:
    # Handle the webhook event with the provided signature and body
    handler.handle(body, signature)
  except InvalidSignatureError:
    # If the signature is invalid, abort the request with a 400 error
    abort(400)

  # Return a response to indicate the webhook event was successfully handled
  return "OK"


# Define a handler for the MessageEvent
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
  # Retrieve the user's message and convert it to lowercase
  user_message = event.message.text.lower()
  reply_message = ""

  # Check the user's message and set the appropriate reply message
  if user_message == "hi":
    reply_message = "Good morning"
  elif user_message == "yes":
    reply_message = "OK"
  elif user_message == "no":
    reply_message = "Why?"
  elif user_message.startswith('/img'):
    payload = json.dumps({
      "key": my_secret4,
      "prompt": user_message.replace("/img", ""),
      "negative_prompt": None,
      "width": "512",
      "height": "512",
      "samples": "1",
      "num_inference_steps": "20",
      "seed": None,
      "guidance_scale": 7.5,
      "safety_checker": "yes",
      "multi_lingual": "no",
      "panorama": "no",
      "self_attention": "no",
      "upscale": "no",
      "embeddings_model": "embeddings_model_id",
      "webhook": None,
      "track_id": None
    })

    headers = {'Content-Type': 'application/json'}

    response = requests.post(urlstdapi, headers=headers, data=payload)

    if response.ok:
      jsonResponse = response.json()
      image_gen_records_collection.insert_one({
        'timestamp':
        timestamp,
        'json_response':
        str(jsonResponse),
        'user_id':
        event.source.user_id
      })
      output_url = jsonResponse['output'][0]
      reply_message = output_url

    else:
      reply_message = "Error: Failed to generate image"
  else:
    reply_message = "I don't know"

  # Save the message to MongoDB
  save_message(event.source.user_id, user_message)

  # Send the reply message back to the user
  line_bot_api.reply_message(event.reply_token,
                             TextSendMessage(text=reply_message))


def save_message(user_id, message):

  # Create a document with user_id, message, and timestamp fields
  message_doc = {
    'user_id': user_id,
    'message': message,
    'timestamp': timestamp
  }

  # Check if the user ID already exists in the master_users collection
  if master_users_collection.find_one({'user_id': user_id}) is None:
    # Retrieve the user's display name
    try:
      profile = line_bot_api.get_profile(user_id)
      display_name = profile.display_name
    except LineBotApiError:
      # Handle error when user profile is not found
      display_name = "Unknown"

    # Insert the user ID and display name into the master_users collection
    master_users_collection.insert_one({
      'user_id': user_id,
      'display_name': display_name,
      'timestamp': timestamp
    })

  # Insert the document into the messages collection
  messages_collection.insert_one(message_doc)


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=81)
