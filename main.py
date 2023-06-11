from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, StickerSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction, MessageAction, URIAction
from pymongo import MongoClient
from datetime import datetime
import json
import pytz
import os
import requests
import time

# StableDiffAPI Url
urlstdapi = "https://stablediffusionapi.com/api/v4/dreambooth"
url_fetch = "https://stablediffusionapi.com/api/v4/dreambooth/fetch"

# Set the timezone to Thailand
timezone = pytz.timezone("Asia/Bangkok")

my_secret = os.environ['LINE_ACCESS_TOKEN']
my_secret2 = os.environ['LINE_SECRET']
my_secret3 = os.environ['MONGO_DB_CONNECTION']
my_secret4 = os.environ['STD_API_KEY']
headers_for_line = {'Content-Type': 'application/json','Authorization':'Bearer'+" "+my_secret}

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
@handler.add(MessageEvent,message=TextMessage)
def handle_message(event):
  # Retrieve the user's message and convert it to lowercase
  user_message = event.message.text.lower()
  global reply_message
  global replytoken 
  global payload
  replytoken = event.reply_token

  # Check the user's message and set the appropriate reply message
  if user_message == "hi":
    reply_message_to_user("Good morning")

  elif user_message == "no":
    reply_message_to_user("why")

  elif user_message.startswith('@curset'):
    json_data = master_users_collection.find_one({'user_id': event.source.user_id},             {"main_model":1,"lora_model": 1})
    main_model = json_data['main_model']
    lora_model = json_data['lora_model']
    reply_message_to_user("🤖Model : " + main_model + "\n️🎚️model : " + lora_model)

  elif user_message.startswith('@setmodel'):
    filter = {'user_id': event.source.user_id}
    newvalues = {"$set": {'main_model': user_message.replace("@setmodel ", "")}}
    master_users_collection.update_one(filter, newvalues)
    reply_message_to_user("Accept new model! : " + user_message)


  elif user_message.startswith('@setlora'):
    filter = {'user_id': event.source.user_id}
    newvalues = {
      "$set": {
        'lora_model': user_message.replace("@setlora ", ""),
      }
    }
    master_users_collection.update_one(filter, newvalues)
    reply_message_to_user("Accept new model! : " + user_message)
    
  elif user_message.startswith('/img'):

    # Set main_model from master_users  to be in json payload
    json_data = (master_users_collection.find_one(
      {'user_id': event.source.user_id}, {"main_model": 1}))
    main_model = json_data['main_model']

    # Set lora model
    json_data1 = (master_users_collection.find_one(
      {'user_id': event.source.user_id}, {"lora_model": 1}))
    lora_model = json_data1['lora_model']

    # If lora in Mongo equal - this mean None for json payload
    if lora_model == "-":
      lora_model = None

    # If not just select normal lora
    else:
      lora_model = json_data1['lora_model']

    # check for negative prompt
    index = user_message.find("--no ")
    negative_prompt = user_message[index + len("--no"):].strip()

    # check for positive prompt
    start_index = user_message.find("/img ") + len("/img")
    end_index = user_message.find("--no ")

    if start_index != -1:
      if end_index != -1:
        positive_prompt = user_message[start_index:end_index].strip()
      else:
        positive_prompt = user_message[start_index:].strip()
    else:
      positive_prompt = None

    # Begin parameter for payload
    payload = json.dumps({
      "key": my_secret4,
      "model_id": main_model,
      "prompt": positive_prompt,
      "negative_prompt": negative_prompt,
      "width": "512",
      "height": "512",
      "samples": "1",
      "num_inference_steps": "31",
      "safety_checker": "no",
      "enhance_prompt": "no",
      "seed": 0,
      "guidance_scale": 7.5,
      "multi_lingual": "no",
      "panorama": "no",
      "self_attention": "no",
      "upscale": "no",
      "embeddings_model": "",
      "lora_model": lora_model,
      "scheduler": "UniPCMultistepScheduler",
      "webhook": None,
      "track_id": None
    })

    headers = {'Content-Type': 'application/json'}

    response = requests.post(urlstdapi, headers=headers, data=payload)

    if response.ok:
      # check status of ok response success or processing?
      data = response.json()
      print (data)
      output_status = data['status']
      output_id = data.get('id')

      # if success
      if output_status == "success":
        jsonResponse = response.json()
        image_gen_records_collection.insert_one({
          'timestamp':
          timestamp,
          'json_response':
          str(jsonResponse),
          'user_id':
          event.source.user_id,
          'track_id':
          output_id
        })
        output_url = jsonResponse['output'][0]
        payload = json.dumps(
        {
          "replyToken": replytoken,
          "messages": [
            {
              "type": "template",
              "altText": "New generated image arrived!",
              "template": {
                "type": "buttons",
                "thumbnailImageUrl": output_url,
                "imageAspectRatio": "square",
                "imageSize": "cover",
                "imageBackgroundColor": "#FFFFFF",
                "title": "Generate success!",
                "text": "Please see seed below",
                "defaultAction": {
                  "type": "uri",
                  "label": "test",
                  "uri": output_url
                },
                "actions": [
                  {
                    "type": "uri",
                    "label": "test",
                    "uri": output_url
                  },
                  {
                    "type": "uri",
                    "label": "test",
                    "uri": output_url}]}}]})
        requests.post('https://api.line.me/v2/bot/message/reply', headers=headers_for_line, data=payload)
        
      #if else, possible to be processing
      elif output_status == "processing":
        jsonResponse = response.json()
        fetch_status = jsonResponse['status']

        # Keep record to check start time of processing
        image_gen_records_collection.insert_one({
          'timestamp':
          timestamp,
          'json_response':
          str(jsonResponse),
          'user_id':
          event.source.user_id
        })

        #whil loop until fetch_status <> processing
        while fetch_status == "processing":
          #wait until 60 second, then fetch data
          time.sleep(60)
          payload = json.dumps({"key": my_secret4, "request_id": output_id})
          headers = {'Content-Type': 'application/json'}

          #Keep response value
          fetch_response = requests.request("POST",
                                            url_fetch,
                                            headers=headers,
                                            data=payload)

          #parse json
          json_fetch_reponse = fetch_response.json()

          fetch_status = json_fetch_reponse['status']

        #select json portion
        output_fetch_url = json_fetch_reponse['output'][0]

        #exit from while then return final result
        reply_message = output_fetch_url
        
        #exit from while then return final result
        line_bot_api.reply_message(event.reply_token,
        TextSendMessage(text=reply_message))

    else:
      reply_message = "Error"
      image_gen_records_collection.insert_one({
        'timestamp':
        timestamp,
        'json_response':
        str(jsonResponse),
        'user_id':
        event.source.user_id
      })
      #send reply to user
      line_bot_api.reply_message(event.reply_token,
        TextSendMessage(text=reply_message))

  else:
    reply_message = "I don't know"
    
    #send reply to user
    line_bot_api.reply_message(event.reply_token,
      TextSendMessage(text=reply_message))

  # Save the message to MongoDB
  save_message(event.source.user_id, user_message)

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


def reply_message_to_user(reply_message):
  line_bot_api.reply_message(replytoken,TextSendMessage(text=reply_message))

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=81)
