from flask import Flask, request, abort, session
from flask_session import Session
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, StickerSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction, MessageAction, URIAction, ImageMessage
from pymongo import MongoClient, UpdateMany
from datetime import datetime
import json
import pytz
import os
import requests
import time
import re
from io import BytesIO
from PIL import Image
import os
import boto3
from botocore.exceptions import ClientError
import threading

##############################################################################
###Warning! Please careful when deploy. Always check 4 things before deplopy###
#1 Check line access token  not test version
#2 Check line secret key token not test version
#3 Mongodb not test version
#4 Make sure no Bug!!
##############################################################################

# StableDiffAPI Url
urlstdapi = "https://stablediffusionapi.com/api/v4/dreambooth"
url_fetch = "https://stablediffusionapi.com/api/v4/dreambooth/fetch"
url_upscale = "https://stablediffusionapi.com/api/v3/super_resolution"

# Set the timezone to Thailand
timezone = pytz.timezone("Asia/Bangkok")

my_secret = os.environ['LINE_ACCESS_TOKEN']  #1 Check line access token  not test version
my_secret2 = os.environ['LINE_SECRET']  #2 Check line secret key token not test version
my_secret3 = os.environ['MONGO_DB_CONNECTION']
my_secret4 = os.environ['STD_API_KEY']
my_secret5 = os.environ['SESSION_SECRET_KEY']
my_secret6 = os.environ['CHAT_GPT']
my_secret7 = os.environ['aws_access_key_id']
my_secret8 = os.environ['bucket_name']
my_secret9 = os.environ['aws_secret_access_key']
my_secret10 = os.environ['MASTER_RESET_KEY']
my_secret11 = os.environ['ADD_UPLOAD_CREDIT_SECRET']

headers_for_line = {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer' + " " + my_secret
}

headers_for_chatgpt = {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer' + " " + my_secret6
}

###variable for imagegen
user_message = ''
var_self_attention = ''
var_width = 512
var_height = 512
var_num_inference_steps = 31
var_seed = 0
var_lora = ''
var_init_iamge = ''
var_strength = ''
controlnet_model0 = ''
emb_model = ''
set_pos = ''
set_neg = ''

###variable for distribute token quota
timecheck = ''

app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
app.secret_key = my_secret5

###aws3control###
aws_access_key_id = my_secret7
aws_secret_access_key = my_secret9
bucket_name = my_secret8  # Replace with your own bucket name
s3_client = boto3.client(
  's3',
  aws_access_key_id=aws_access_key_id,
  aws_secret_access_key=aws_secret_access_key)  # Create an S3 client

line_bot_api = LineBotApi(my_secret)
handler = WebhookHandler(my_secret2)

# Connect to MongoDB Atlas
client = MongoClient(my_secret3)

# Specify the database and collection
db = client['line_bot_database']  #3 Mongodb not test version
messages_collection = db['messages']
master_users_collection = db['master_users']
image_gen_records_collection = db['image_gen_records_collection']
model_master_collection = db["model_master"]
lora_and_emb_master_collection = db["lora_and_emb_master"]
pure_message_gpt_collection = db["pure_message_gpt"]
history_pure_message_gpt_collection = db["history_pure_message_gpt"]
payment_collection = db["payment"]
credit_refill_collection = db["credit_refill"]


# Get the current time in Thailand timezone
current_time = datetime.now(timezone)

# Format the timestamp as a string
timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')

##########################################Database control##########################################
##########################################Database control##########################################
##########################################Database control##########################################

#Refill free token to user every beginning of the month
def loop_function():
    while True:
      print(timestamp)

      if current_time.day == 1:
        x = 20000
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
    


# Create a thread for the loop function
loop_thread = threading.Thread(target=loop_function)
loop_thread.start()  # Start the loop thread
##########################################Database control##########################################
##########################################Database control##########################################
##########################################Database control##########################################




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
@handler.add(MessageEvent, message=(ImageMessage, TextMessage))
def handle_message(event):

  global reply_message
  global payload

  # Retrieve the reply token from the session data or generate a new one
  replytoken = session.get("replytoken")
  if replytoken is None:
    replytoken = event.reply_token
    session["replytoken"] = replytoken

  lineUserId = event.source.user_id
  print(timestamp + ": " + "input_user: " + lineUserId)
  print(timestamp + ": " + "input_reply_token: " + replytoken)

  if isinstance(event.message, ImageMessage):

    json_data = (master_users_collection.find_one(
      {'user_id': event.source.user_id}, {
        "autobeauty": 1,
        "upload_credit": 1
      }))

    #Check is credit enought to upload?
    pull_credit = json_data['upload_credit']
    if pull_credit < 1:
      reply_message_to_user(
        "Upload credit is not enought😭, Contact admin for more credit @ https://www.facebook.com/onemaigpt/"
      )

    #Accept for next process
    else:
      check_beauty = str(json_data['autobeauty'])

      if check_beauty == "False":
        print("ok1")
        message_id = event.message.id
        message_content = line_bot_api.get_message_content(message_id)

        print("ok2")
        # Convert the image to PNG
        image = Image.open(BytesIO(message_content.content))
        image_png = image.convert("RGBA")

        print("ok3")
        # Save the PNG image to a buffer
        buffer = BytesIO()
        image_png.save(buffer, "PNG")
        buffer.seek(0)

        print("ok4")
        # Upload the PNG image to Line and get the URL
        image_url = upload_image(message_id, buffer)

        print(image_url)

        #deduct credit
        pull_credit -= 1
        print(pull_credit)
        newvalues = {"$set": {'upload_credit': pull_credit}}
        master_users_collection.update_one(json_data, newvalues)

        #Below command will send back image url
        line_bot_api.reply_message(event.reply_token,
                                   TextMessage(text=image_url))

      else:
        print("ok1beauty")
        message_id = event.message.id
        message_content = line_bot_api.get_message_content(message_id)

        print("ok2beauty")
        # Convert the image to PNG
        image = Image.open(BytesIO(message_content.content))
        image_png = image.convert("RGBA")

        print("ok3beauty")
        # Save the PNG image to a buffer
        buffer = BytesIO()
        image_png.save(buffer, "PNG")
        buffer.seek(0)

        print("ok4beauty")
        # Upload the PNG image to Line and get the URL
        image_url = upload_image(message_id, buffer)

        if "replytoken" in session:
          replytoken = session.get("replytoken")
          payload = json.dumps({
            "key": my_secret4,
            "controlnet_model": None,
            "controlnet_type": None,
            "model_id": "bro623jbfe32",
            "prompt": "masterpiece portrait photography Korean girl",
            "negative_prompt":
            "extra fingers, extra hands, extra arms, worst quality, bad quality, bad face, bad anatomy",
            "width": 512,
            "height": 768,
            "samples": "1",
            "num_inference_steps": 31,
            "safety_checker": "no",
            "enhance_prompt": "no",
            "seed": 0,
            "guidance_scale": 7.5,
            "strength": 0.3,  #param for image2image
            "lora_model": None,
            "lora_strength": None,  #param for image2image
            "init_image": image_url,  #param for image2image/inpaint
            "mask_image": None,  #param for image2image/inpaint
            "multi_lingual": "no",
            "panorama": "no",
            "self_attention": "no",
            "clip_skip": 2,
            "upscale": "no",
            "embeddings_model": None,
            "scheduler": "UniPCMultistepScheduler",
            "webhook": None,
            "track_id": None,
          })

          headers = {'Content-Type': 'application/json'}

          response = requests.post(
            'https://stablediffusionapi.com/api/v4/dreambooth/img2img',
            headers=headers,
            data=payload)

          if response.ok:
            # check status of ok response success or processing?
            data = response.json()
            #print(data)
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
              #output_W = jsonResponse['W']
              #output_H = jsonResponse['H']
              output_model = jsonResponse['meta']['model_id']
              output_W = jsonResponse['meta']['W']
              output_H = jsonResponse['meta']['H']
              output_seed = jsonResponse['meta']['seed']
              output_steps = jsonResponse['meta']['steps']
              output_lora = jsonResponse['meta']['lora']

              #found bug that cannot reply None value for lora so add "-" if lora is None
              if output_lora == None:
                output_lora = "-"

              payload = json.dumps({
                "replyToken":
                replytoken,
                "messages": [{
                  "type": "template",
                  "altText": "New image arrived!",
                  "template": {
                    "type":
                    "buttons",
                    "thumbnailImageUrl":
                    output_url,
                    "imageAspectRatio":
                    "square",
                    "imageSize":
                    "cover",
                    "imageBackgroundColor":
                    "#FFFFFF",
                    "title":
                    "Model : " + output_model,
                    "text":
                    "Steps : " + str(output_steps) + " Id : " + str(output_id),
                    "defaultAction": {
                      "type": "uri",
                      "label": "test",
                      "uri": output_url
                    },
                    "actions": [{
                      "type": "uri",
                      "label": "L : " + output_lora,
                      "uri": output_url
                    }, {
                      "type": "message",
                      "label": "Upscale",
                      "text": "@upscale " + output_url
                    }, {
                      "type":
                      "uri",
                      "label":
                      "Size : " + str(output_W) + " * " + str(output_H),
                      "uri":
                      output_url
                    }, {
                      "type": "message",
                      "label": "Seed_No : " + str(output_seed),
                      "text": "@check " + str(output_id)
                    }]
                  }
                }]
              })
              print(timestamp + ": " + "image_completed_for_user: " +
                    lineUserId)
              print(timestamp + ": " + "image_completed_for_reply_token: " +
                    replytoken)

              #deduct credit
              pull_credit -= 1
              print(pull_credit)
              newvalues = {"$set": {'upload_credit': pull_credit}}

              master_users_collection.update_one(json_data, newvalues)
              requests.post('https://api.line.me/v2/bot/message/reply',
                            headers=headers_for_line,
                            data=payload)

            #if else, possible to be processing
            elif output_status == "processing":
              print("Entering processing")
              jsonResponse = response.json()
              fetch_status = jsonResponse['status']

              # Keep record to check start time of processing
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

              #whil loop until fetch_status <> processing
              while fetch_status == "processing":
                #wait until 60 second, then fetch data
                time.sleep(15)
                payload = json.dumps({
                  "key": my_secret4,
                  "request_id": output_id
                })
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

              else:
                output_fetch_url = json_fetch_reponse['output'][0]
                #exit from while then return final result
                reply_message = output_fetch_url + " : " + str(output_id)

                #exit from while then return final result
                print("image_completed_for_user: " + lineUserId)
                print("image_completed_for_reply_token: " + replytoken)
                print("result come after processing pending")

                #deduct credit
                pull_credit -= 1
                print(pull_credit)
                newvalues = {"$set": {'upload_credit': pull_credit}}

                #send result to user
                line_bot_api.reply_message(event.reply_token,
                                           TextSendMessage(text=reply_message))

            else:
              jsonResponse = response.json()
              reply_message_to_user(str(jsonResponse))

            #When error send raw json from stdapi to user
          else:
            jsonResponse = response.json()
            #terminal inform error
            print("error")
            #send reply to user
            reply_message_to_user(str(jsonResponse))

        else:
          print("Reply token not found")

  elif isinstance(event.message, TextMessage):
    user_message = event.message.text

    # Check the user's message and set the appropriate reply message
    if user_message == "hi":
      reply_message_to_user("Good morning")

    ##############################################################################
    ###This command is to reset new value when update new function to OnemaiGPT###
    ##############################################################################
    elif user_message.startswith(my_secret10):
      # Define the update criteria
      filter_criteria = {}
      # Define the update operation
      update_operation = {
        '$set': {
          'set_pos': '-',
          'set_neg': '-',
          'autobeauty': True,
          'upload_credit': 20,
          'emb_model':"-",
          'eco_mode': False,
          'freetoken':25000
        }
      }
      # Create an UpdateMany object
      update_many = UpdateMany(filter_criteria, update_operation)
      # Execute the update operation
      result = master_users_collection.bulk_write([update_many])
      reply_message_to_user("Update success!")

    #add upload credit 20 credits
    elif user_message.startswith(my_secret11):

      #specify user_id
      target_id = user_message.replace(my_secret11, "")

      if master_users_collection.find_one({'user_id': target_id},
                                          {"upload_credit: 1"}) is not None:
        json_data = (master_users_collection.find_one({'user_id': target_id}, {
          "display_name": 1,
          "upload_credit": 1
        }))
        pull_user_id = target_id
        print(pull_user_id)
        pull_display_name = json_data['display_name']
        print(pull_display_name)
        pull_credit = json_data['upload_credit']
        pull_credit += 20
        print(pull_credit)
        filter = {'user_id': target_id}
        newvalues = {"$set": {'upload_credit': pull_credit}}
        master_users_collection.update_one(filter, newvalues)
        credit_refill_collection.insert_one({
          'user_id':
          target_id,
          'display_name':
          pull_display_name,
          'timestamp':
          timestamp,
          'upload_credit_refill':
          20,
          'upload_credit_refill_balance':
          pull_credit
        })
        reply_message_to_user("Add 20 upload credits to " + pull_display_name +
                              " Success! " + "Upload_credit_balance : " +
                              str(pull_credit))

      else:
        reply_message_to_user("User not found!")

    elif user_message == "no":
      reply_message_to_user("why")

    elif user_message == "@autobeautyon":
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'autobeauty': True,
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user("Autobeauty was turned on, please enjoy!")

    elif user_message == "@autobeautyoff":
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'autobeauty': False,
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user(
        "Autobeauty was turn off, sending image will be converted to png image url."
      )

    elif user_message.startswith('@clearchat'):
      delete_filter = {'user_id': event.source.user_id}
      result = pure_message_gpt_collection.delete_many(delete_filter)
      reply_message_to_user("All chat deleted!")

    elif user_message.startswith('@callmopho'):
      query_condition = {
        "GPT_type_mainModel":
        "Photography"  # Modify the field and value as per your query condition
      }

      # Query data from MongoDB based on the condition
      query_result = model_master_collection.find(query_condition)

      # Create an empty array to store the data
      data = []

      # Iterate over the query result and insert into the data array
      for item in query_result:
        thumbnail_image_url = item["GPT_model_image_link"]
        GPT_CIVmodel_name = item["GPT_CIVmodel_name"]
        Title = item["Title"]
        GPT_sample_prompt = item["GPT_sample_prompt"]
        new_member = {
          "thumbnailImageUrl":
          thumbnail_image_url,
          "imageBackgroundColor":
          "#FFFFFF",
          "title":
          GPT_CIVmodel_name,
          "text":
          "description",
          "defaultAction": {
            "type": "uri",
            "label": "View detail",
            "uri": "http://example.com/page/123"
          },
          "actions": [{
            "type": "message",
            "label": "Set Model",
            "text": "@setmodel " + Title
          }, {
            "type": "message",
            "label": "Sample Prompt",
            "text": GPT_sample_prompt
          }]
        }
        data.append(new_member)

        payload = json.dumps({
          "replyToken":
          replytoken,
          "messages": [{
            "type": "template",
            "altText": "this is a carousel template",
            "template": {
              "type": "carousel",
              "columns": data,
              "imageAspectRatio": "square",
              "imageSize": "cover"
            }
          }]
        })

      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@callmogen'):
      query_condition = {
        "GPT_type_mainModel":
        "General"  # Modify the field and value as per your query condition
      }

      # Query data from MongoDB based on the condition
      query_result = model_master_collection.find(query_condition)

      # Create an empty array to store the data
      data = []

      # Iterate over the query result and insert into the data array
      for item in query_result:
        thumbnail_image_url = item["GPT_model_image_link"]
        GPT_CIVmodel_name = item["GPT_CIVmodel_name"]
        Title = item["Title"]
        GPT_sample_prompt = item["GPT_sample_prompt"]
        new_member = {
          "thumbnailImageUrl":
          thumbnail_image_url,
          "imageBackgroundColor":
          "#FFFFFF",
          "title":
          GPT_CIVmodel_name,
          "text":
          "description",
          "defaultAction": {
            "type": "uri",
            "label": "View detail",
            "uri": "http://example.com/page/123"
          },
          "actions": [{
            "type": "message",
            "label": "Set Model",
            "text": "@setmodel " + Title
          }, {
            "type": "message",
            "label": "Sample Prompt",
            "text": GPT_sample_prompt
          }]
        }
        data.append(new_member)

        payload = json.dumps({
          "replyToken":
          replytoken,
          "messages": [{
            "type": "template",
            "altText": "this is a carousel template",
            "template": {
              "type": "carousel",
              "columns": data,
              "imageAspectRatio": "square",
              "imageSize": "cover"
            }
          }]
        })

      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@callmocar'):
      query_condition = {
        "GPT_type_mainModel":
        "Cartoon"  # Modify the field and value as per your query condition
      }

      # Query data from MongoDB based on the condition
      query_result = model_master_collection.find(query_condition)

      # Create an empty array to store the data
      data = []

      # Iterate over the query result and insert into the data array
      for item in query_result:
        thumbnail_image_url = item["GPT_model_image_link"]
        GPT_CIVmodel_name = item["GPT_CIVmodel_name"]
        Title = item["Title"]
        GPT_sample_prompt = item["GPT_sample_prompt"]
        new_member = {
          "thumbnailImageUrl":
          thumbnail_image_url,
          "imageBackgroundColor":
          "#FFFFFF",
          "title":
          GPT_CIVmodel_name,
          "text":
          "description",
          "defaultAction": {
            "type": "uri",
            "label": "View detail",
            "uri": thumbnail_image_url
          },
          "actions": [{
            "type": "message",
            "label": "Set Model",
            "text": "@setmodel " + Title
          }, {
            "type": "message",
            "label": "Sample Prompt",
            "text": GPT_sample_prompt
          }]
        }
        data.append(new_member)

        payload = json.dumps({
          "replyToken":
          replytoken,
          "messages": [{
            "type": "template",
            "altText": "this is a carousel template",
            "template": {
              "type": "carousel",
              "columns": data,
              "imageAspectRatio": "square",
              "imageSize": "cover"
            }
          }]
        })

      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@callmomsc'):
      query_condition = {
        "GPT_type_mainModel":
        "Msc."  # Modify the field and value as per your query condition
      }

      # Query data from MongoDB based on the condition
      query_result = model_master_collection.find(query_condition)

      # Create an empty array to store the data
      data = []

      # Iterate over the query result and insert into the data array
      for item in query_result:
        thumbnail_image_url = item["GPT_model_image_link"]
        GPT_CIVmodel_name = item["GPT_CIVmodel_name"]
        Title = item["Title"]
        GPT_sample_prompt = item["GPT_sample_prompt"]
        new_member = {
          "thumbnailImageUrl":
          thumbnail_image_url,
          "imageBackgroundColor":
          "#FFFFFF",
          "title":
          GPT_CIVmodel_name,
          "text":
          "description",
          "defaultAction": {
            "type": "uri",
            "label": "View detail",
            "uri": "http://example.com/page/123"
          },
          "actions": [{
            "type": "message",
            "label": "Set Model",
            "text": "@setmodel " + Title
          }, {
            "type": "message",
            "label": "Sample Prompt",
            "text": GPT_sample_prompt
          }]
        }
        data.append(new_member)

        payload = json.dumps({
          "replyToken":
          replytoken,
          "messages": [{
            "type": "template",
            "altText": "this is a carousel template",
            "template": {
              "type": "carousel",
              "columns": data,
              "imageAspectRatio": "square",
              "imageSize": "cover"
            }
          }]
        })

      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@callmodel'):
      payload = json.dumps({
        "replyToken":
        replytoken,
        "messages": [{
          "type": "flex",
          "altText": "Flex Message",
          "contents": {
            "type": "bubble",
            "size": "micro",
            "header": {
              "type":
              "box",
              "layout":
              "vertical",
              "contents": [{
                "type": "text",
                "text": "🏷️ModelType",
                "weight": "bold",
                "size": "18px",
                "color": "#FFFFFF"
              }],
              "backgroundColor":
              "#32CD32"
            },
            "hero": {
              "type":
              "box",
              "layout":
              "vertical",
              "contents": [{
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "General",
                  "text": "@callmogen"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "Cartoon",
                  "text": "@callmocar"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "Photography",
                  "text": "@callmopho"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "Msc.",
                  "text": "@callmomsc"
                }
              }]
            }
          }
        }]
      })
      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@calllora'):
      query_condition = {
        "$or": [{
          "GPT_LoraOrEmbedding": "Lora"
        }, {
          "GPT_LoraOrEmbedding": "Embedding"
        }]
      }

      # Query data from MongoDB based on the condition
      query_result = lora_and_emb_master_collection.find(query_condition)

      # Create an empty array to store the data
      data = []

      for item in query_result:

        thumbnail_image_url = item["GPT_LoraEmbedding_Image"]
        GPT_CIVmodel_name = item["title"]
        GPT_LoraEmbedding_Name = item["GPT_LoraEmbedding_Name"]
        command_type = item["command_type"]

        new_member = {
          "thumbnailImageUrl":
          thumbnail_image_url,
          "imageBackgroundColor":
          "#FFFFFF",
          "title":
          GPT_CIVmodel_name,
          "text":
          "description",
          "defaultAction": {
            "type": "uri",
            "label": "View detail",
            "uri": thumbnail_image_url
          },
          "actions": [{
            "type": "message",
            "label": "Set Model",
            "text": command_type + GPT_LoraEmbedding_Name
          }]
        }

        data.append(new_member)

        payload = json.dumps({
          "replyToken":
          replytoken,
          "messages": [{
            "type": "template",
            "altText": "this is a carousel template",
            "template": {
              "type": "carousel",
              "columns": data,
              "imageAspectRatio": "square",
              "imageSize": "cover"
            }
          }]
        })

      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@callcont'):
      payload = json.dumps({
        "replyToken":
        replytoken,
        "messages": [{
          "type": "flex",
          "altText": "Flex Message",
          "contents": {
            "type": "bubble",
            "size": "micro",
            "header": {
              "type":
              "box",
              "layout":
              "vertical",
              "contents": [{
                "type": "text",
                "text": "🕹️Controlnet_List",
                "color": "#FFFFFF",
                "size": "18px",
                "weight": "bold"
              }],
              "backgroundColor":
              "#32CD32"
            },
            "body": {
              "type":
              "box",
              "layout":
              "vertical",
              "contents": [{
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "CANNY",
                  "text": "@setcont canny"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "DEPTH",
                  "text": "@setcont depth"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "MLSD",
                  "text": "@setcont mlsd"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "OPENPOSE",
                  "text": "@setcont openpose"
                }
              }, {
                "type": "button",
                "action": {
                  "type": "message",
                  "label": "SCRIBBLE",
                  "text": "@setcont scribble"
                }
              }]
            }
          }
        }]
      })
      requests.post('https://api.line.me/v2/bot/message/reply',
                    headers=headers_for_line,
                    data=payload)

    elif user_message.startswith('@check'):
      json_data = image_gen_records_collection.find_one(
        {'track_id': int(user_message.replace("@check ", ""))}, {
          "track_id": 1,
          "json_response": 1
        })

      if json_data is not None:
        track_id = json_data['track_id']
        json_response = json_data['json_response']
        reply_message_to_user(str(track_id) + str(json_response))
      else:
        reply_message_to_user("No record found with the specified track_id")

    elif user_message.startswith('@curset'):


     
      json_data = master_users_collection.find_one(
        {'user_id': event.source.user_id}, {
          "autobeauty": 1,
          "main_model": 1,
          "lora_model": 1,
          "controlnet_model0": 1,
          "emb_model": 1,
          "set_pos": 1,
          "set_neg": 1,
          "upload_credit": 1,
          "freetoken": 1,
          "eco_mode": 1
        })
      
      autobeauty = str(json_data['autobeauty'])
      main_model = json_data['main_model']
      lora_model = json_data['lora_model']
      controlnet_model0 = json_data['controlnet_model0']
      emb_model = json_data['emb_model']
      pos_result = json_data['set_pos']
      neg_result = json_data['set_neg']
      upload_credit = str(json_data['upload_credit'])
      free_token = str(json_data['freetoken'])
      eco_mode = str(json_data['eco_mode'])
      reply_message_to_user("🤖Model : " + main_model + "\n️🎚️lora_model : " +
                            lora_model + "\n🎚️emb_model :" + emb_model +
                            "\n️🕹️control_net :" + controlnet_model0 +
                            "\n️✅set_pos :" + pos_result + "\n️🚫set_neg :" +
                            neg_result + "\n💋auto_beauty :" + autobeauty +
                            "\n📤upload_credit :" + upload_credit + "\n🪙freetoken_left :" + free_token
                            + "\n🍃Eco_mode :" + eco_mode)

    elif user_message.startswith('@payment'):
      json_data = master_users_collection.find_one(
        {'user_id': event.source.user_id}, {"display_name": 1})
      display_name = json_data['display_name']
      payment_collection.insert_one({
        'user_id': event.source.user_id,
        'display_name': display_name,
        'timestamp': timestamp,
      })
      reply_message_to_user(
        "Payment request was received please contact https://www.facebook.com/onemaigpt/"
      )

    elif user_message.startswith('@setmodel'):
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'main_model': user_message.replace("@setmodel ", "")
        }
      }
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

    elif user_message.startswith('@setemb'):
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'emb_model': user_message.replace("@setemb ", ""),
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user("Accept new model! : " + user_message)

    elif user_message.startswith('@setcont'):
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'controlnet_model0': user_message.replace("@setcont ", ""),
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user("Accept new controlnet! : " + user_message)

    elif user_message.startswith('@setpos'):
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'set_pos': user_message.replace("@setpos ", "") + " ",
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user("Accept new setpos! : " + user_message)

    elif user_message.startswith('@setneg'):
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'set_neg': user_message.replace("@setneg ", ""),
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user("Accept new setneg! : " + user_message)

    elif user_message.startswith('@clearlora_emb'):
      filter = {'user_id': event.source.user_id}
      newvalues = {
        "$set": {
          'lora_model': "-",
          'emb_model': "-",
          'set_pos': "-",
          'set_neg': "-"
        }
      }
      master_users_collection.update_one(filter, newvalues)
      reply_message_to_user("Clear lora and embedding!")

    elif user_message.startswith('@upscale'):
      payload = json.dumps({
        "key": my_secret4,
        "url": user_message.replace("@upscale ", ""),
        "scale": 3,
        "webhook": None
      })
      headers = {'Content-Type': 'application/json'}
      response = requests.post(url_upscale, headers=headers, data=payload)

      if response.ok:
        # check status of ok response success or processing?
        data = response.json()
        print(data)
        output_url = data['output']
        reply_message_to_user("Upscale complete! : " + output_url)

    elif user_message.startswith('@eco'):
      json_data = (master_users_collection.find_one(
      {'user_id': event.source.user_id}, {
        "eco_mode": 1
      }))
      if json_data['eco_mode'] == False:
        filter = {'user_id': event.source.user_id}
        newvalues = {"$set": {'eco_mode': True}}
        master_users_collection.update_one(filter, newvalues)
        reply_message_to_user("🤖OnemaiGPT(Eco🍃) : Eco mode turn on!")
      else:
        filter = {'user_id': event.source.user_id}
        newvalues = {"$set": {'eco_mode': False}}
        master_users_collection.update_one(filter, newvalues)
        reply_message_to_user("🤖OnemaiGPT(💬) : Conversation mode turn on!")

    elif user_message.startswith('/img'):

      #check for init_image
      if user_message.find("http") > -1:
        x = user_message.index("http")
        y = user_message.index(".png")
        z = user_message[x:y]
        var_init_iamge = z + ".png"
        remove_http = user_message.replace(z + ".png", "")
        user_message = remove_http
        urlstdapi = "https://stablediffusionapi.com/api/v4/dreambooth/img2img"
        print(var_init_iamge)
        print(urlstdapi)
      else:
        var_init_iamge = None
        urlstdapi = "https://stablediffusionapi.com/api/v4/dreambooth"

      #check for @cont and remove from prompt!
      if user_message.find("@cont") > -1:
        urlstdapi = "https://stablediffusionapi.com/api/v5/controlnet"
        json_data = (master_users_collection.find_one(
          {'user_id': event.source.user_id}, {"controlnet_model0": 1}))
        controlnet_model0 = json_data['controlnet_model0']
        x = user_message.replace("@cont","")
        user_message = x
        print(controlnet_model0)
      else:
        controlnet_model0 = None

      #check for image strength
      if user_message.find("--str") > -1:
        x = user_message.index("--str")
        y = user_message[x:]
        var_strength = (re.search(r'\d+\.\d+', y).group())
        z = user_message.replace(y, "")
        user_message = z
        print(float(var_strength))
        print(user_message)
      else:
        var_strength = float(0.3)

      #check for sefl attention
      if user_message.find("@hf") > -1:
        var_self_attention = "yes"
        #when chagne global variable, there must be new local var to save new value for global var
        x = user_message.replace("@hf", "")
        user_message = x
      else:
        var_self_attention = "no"

      #check for portrait ratio
      if user_message.find("--arp") > -1:
        var_height = 768
        #when chagne global variable, there must be new local var to save new value for global var
        x = user_message.replace("--arp", "")
        user_message = x
      else:
        var_height = 512

      #check for landscape ratio
      if user_message.find("--arl") > -1:
        var_width = 768
        #when chagne global variable, there must be new local var to save new value for global var
        x = user_message.replace("--arl", "")
        user_message = x
      else:
        var_width = 512

      #check for step
      if user_message.find("--step") > -1:
        #check where step begin
        x = user_message.index("--step")
        #read the whole step (step with number)
        y = user_message[x:]
        #assign variable for number after --step
        var_num_inference_steps = re.search(r'\d+', y).group()
        #delete --stepxx from user message
        z = user_message.replace(y, "")
        #user message after delete --stepxx
        user_message = z
      else:
        var_num_inference_steps = 31

      #check for seed
      if user_message.find("--seed") > -1:
        #check where step begin
        x = user_message.index("--seed")
        #read the whole step (step with number)
        y = user_message[x:]
        #assign variable for number after --step
        var_seed = re.search(r'\d+', y).group()
        #delete --stepxx from user message
        z = user_message.replace(y, "")
        #user message after delete --stepxx
        user_message = z
      else:
        var_seed = 0

      # Set main_model from master_users  to be in json payload
      json_data = (master_users_collection.find_one(
        {'user_id': event.source.user_id}, {"main_model": 1}))
      main_model = json_data['main_model']
      print(main_model)
      # Set lora model
      json_data1 = (master_users_collection.find_one(
        {'user_id': event.source.user_id}, {"lora_model": 1}))
      lora_model = json_data1['lora_model']
      print(lora_model)
      # If lora in Mongo equal - this mean None for json payload
      if lora_model == "-":
        lora_model = None

      # Set emb model
      json_data2 = (master_users_collection.find_one(
        {'user_id': event.source.user_id}, {"emb_model": 1}))
      emb_model = json_data2['emb_model']

      # If lora in Mongo equal - this mean None for json payload
      if emb_model == "-":
        emb_model = None
      # If not just select normal lora
      # else:
      #lora_model =json_data1['lora_model']
      # check for negative prompt
      #check set_pos
      json_data3 = (master_users_collection.find_one(
        {'user_id': event.source.user_id}, {"set_pos": 1}))
      set_pos = json_data3['set_pos']
      # If lora in Mongo equal - this mean None for json payload
      if set_pos == "-":
        set_pos = ""

      #check set_neg
      json_data4 = (master_users_collection.find_one(
        {'user_id': event.source.user_id}, {"set_neg": 1}))
      set_neg = json_data4['set_neg']
      # If lora in Mongo equal - this mean None for json payload
      if set_neg == "-":
        set_neg = ""

      index = user_message.find("--no ")
      if index != -1:
        # Extract the negative prompt
        negative_prompt = user_message[index + len("--no"):].strip()
      else:
        # No "--no" found, set negative prompt to empty string
        negative_prompt = ""

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

      if "replytoken" in session:
        replytoken = session.get("replytoken")
        # Begin parameter for payload
        # test controlnet name
        print(controlnet_model0)
        print(urlstdapi)
        payload = json.dumps({
          "key": my_secret4,
          "controlnet_model": controlnet_model0,
          "controlnet_type": controlnet_model0,
          "model_id": main_model,
          "prompt": set_pos + positive_prompt + " sfw",
          "negative_prompt": set_neg + negative_prompt + " nsfw",
          "width": var_width,
          "height": var_height,
          "samples": "1",
          "num_inference_steps": var_num_inference_steps,
          "safety_checker": "no",
          "enhance_prompt": "no",
          "seed": var_seed,
          "guidance_scale": 7.5,
          "strength": var_strength,  #param for image2image
          "lora_model": lora_model,
          "lora_strength": 0.6,  #param for image2image
          "init_image": var_init_iamge,  #param for image2image/inpaint
          "mask_image": None,  #param for image2image/inpaint
          "multi_lingual": "no",
          "panorama": "no",
          "self_attention": var_self_attention,
          "clip_skip": 1,
          "upscale": "no",
          "embeddings_model": emb_model,
          "scheduler": "UniPCMultistepScheduler",
          "webhook": None,
          "track_id": None
        })

        headers = {'Content-Type': 'application/json'}

        response = requests.post(urlstdapi, headers=headers, data=payload)

        if response.ok:
          # check status of ok response success or processing?
          data = response.json()
          #print(data)
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
            #output_W = jsonResponse['W']
            #output_H = jsonResponse['H']
            output_model = jsonResponse['meta']['model_id']
            output_W = jsonResponse['meta']['W']
            output_H = jsonResponse['meta']['H']
            output_seed = jsonResponse['meta']['seed']
            output_steps = jsonResponse['meta']['steps']
            output_lora = jsonResponse['meta']['lora']

            #found bug that cannot reply None value for lora so add "-" if lora is None
            if output_lora == None:
              output_lora = "-"

            payload = json.dumps({
              "replyToken":
              replytoken,
              "messages": [{
                "type": "template",
                "altText": "New image arrived!",
                "template": {
                  "type":
                  "buttons",
                  "thumbnailImageUrl":
                  output_url,
                  "imageAspectRatio":
                  "square",
                  "imageSize":
                  "cover",
                  "imageBackgroundColor":
                  "#FFFFFF",
                  "title":
                  "Model : " + output_model,
                  "text":
                  "Steps : " + str(output_steps) + " Id : " + str(output_id),
                  "defaultAction": {
                    "type": "uri",
                    "label": "test",
                    "uri": output_url
                  },
                  "actions": [{
                    "type": "uri",
                    "label": "L : " + output_lora,
                    "uri": output_url
                  }, {
                    "type": "message",
                    "label": "Upscale",
                    "text": "@upscale " + output_url
                  }, {
                    "type":
                    "uri",
                    "label":
                    "Size : " + str(output_W) + " * " + str(output_H),
                    "uri":
                    output_url
                  }, {
                    "type": "message",
                    "label": "Seed_No : " + str(output_seed),
                    "text": "@check " + str(output_id)
                  }]
                }
              }]
            })
            print(timestamp + ": " + "image_completed_for_user: " + lineUserId)
            print(timestamp + ": " + "image_completed_for_reply_token: " +
                  replytoken)
            requests.post('https://api.line.me/v2/bot/message/reply',
                          headers=headers_for_line,
                          data=payload)

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
              event.source.user_id,
              'track_id':
              output_id
            })

            #whil loop until fetch_status <> processing
            #whil loop until fetch_status <> processing
            while fetch_status == "processing":
              #wait until 60 second, then fetch data
              time.sleep(60)
              payload = json.dumps({
                "key": my_secret4,
                "request_id": output_id
              })
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
              reply_message = output_fetch_url + " : " + str(output_id)

              #exit from while then return final result
              print("image_completed_for_user: " + lineUserId)
              print("image_completed_for_reply_token: " + replytoken)
              print("result come after processing pending")
              line_bot_api.reply_message(event.reply_token,
                                         TextSendMessage(text=reply_message))

          else:
            jsonResponse = response.json()
            reply_message_to_user(str(jsonResponse))

          #When error send raw json from stdapi to user
        else:
          jsonResponse = response.json()
          #terminal inform error
          print("error")
          #send reply to user
          reply_message_to_user(str(jsonResponse))

      else:
        print("Reply token not found")

    #sent other message to chatgpt
    else:
      json_data = (master_users_collection.find_one(
      {'user_id': event.source.user_id}, {
        "freetoken": 1,"eco_mode": 1
      }))
      eco_mode = json_data['eco_mode']

      #Check gpt mode eco or conversation? if conver->
      if eco_mode == False:
        #Check is credit enought to upload?
        pull_freetoken = json_data['freetoken']
        if pull_freetoken < 1:
          reply_message_to_user(
            "Free token is not enought😭, Contact admin for buying credit @ https://www.facebook.com/onemaigpt/"
          )
        else:
          #Record message to message_gpt
          message_gpt = {
            'user_id': event.source.user_id,
            'message': user_message,
            'timestamp': timestamp,
            'gpt_role': "user"
          }
          pure_message_gpt_collection.insert_one(message_gpt)
          print(message_gpt)
    
          #query user message to input chatgpt
          query_condition = {"user_id": event.source.user_id}
          query_result = pure_message_gpt_collection.find(query_condition)
    
          # Create an empty array to store the data
          data = [{"role": "system", "content": "You are helpul assistant. You are male"}]
    
          for item in query_result:
            filtered_user_messages = item["message"]
            filtered_role = item["gpt_role"]
    
            new_member = {"role": filtered_role, "content": filtered_user_messages}
    
            data.append(new_member)
    
            payload = json.dumps({
              "model": "gpt-3.5-turbo",
              "messages": data,
              "temperature": 0.7
            })
    
          response = requests.post('https://api.openai.com/v1/chat/completions',
                                   headers=headers_for_chatgpt,
                                   data=payload)
    
          print(response)
          if response.ok:
            # check status of ok response success or processing?
            gpt_reply = response.json()
            print(gpt_reply)
            gpt_output_role = gpt_reply['choices'][0]['message']['role']
            gpt_output_content = gpt_reply['choices'][0]['message']['content']
            gpt_output_prompt_tokens = gpt_reply['usage']['prompt_tokens']
            gpt_output_completetion_tokens = gpt_reply['usage']['completion_tokens']
            gpt_output_total_tokens = gpt_reply['usage']['total_tokens']
    
            #record response from gpt to mongodb
            message_gpt = {
              'user_id': event.source.user_id,
              'message': gpt_output_content,
              'timestamp': timestamp,
              'gpt_role': gpt_output_role,
              'gpt_prompt_token': gpt_output_prompt_tokens,
              'gpt_completion_token' : gpt_output_completetion_tokens,
              'gpt_total_tokens' : gpt_output_total_tokens,
              'input_message' : user_message
            }
    
            pure_message_gpt_collection.insert_one(message_gpt)
    
            reply_message = ("🤖OnemaiGPT(💬): ") + gpt_output_content
    
            #send reply to user
            line_bot_api.reply_message(event.reply_token,
                                       TextSendMessage(text=reply_message))
  
            #decrease freetoken after complete
            freetoken_left = pull_freetoken - gpt_output_total_tokens
  
            #update freetoken left to user
            filter = {'user_id': event.source.user_id}
            newvalues = {"$set": {'freetoken': freetoken_left}}
            master_users_collection.update_one(filter, newvalues)
    
            #keep chat gpt history chat for counting each user's token #payment
            history_pure_message_gpt_collection.insert_one(message_gpt)
            
          else:
            reply_message = "❗Error ลองพิมพ์ @clearchat เพื่อล้างประวัติการ chat ก่อนนะ! " + str(
              response)
    
        # Save the message to MongoDB
        save_message(event.source.user_id, user_message)
        
      #Check gpt mode eco or conversation? if eco->
      else:
        if eco_mode == True:
          #Check is credit enought to upload?
          pull_freetoken = json_data['freetoken']
          if pull_freetoken < 1:
            reply_message_to_user(
              "Free token is not enought😭, Contact admin for buying credit @ https://www.facebook.com/onemaigpt/"
            )
          else:
            #Record message to message_gpt
            message_gpt = {
              'user_id': event.source.user_id,
              'message': user_message,
              'timestamp': timestamp,
              'gpt_role': "user"
            }
            print(message_gpt)
      
     
            # Create an empty array to store the data
            data = [{"role": "system", "content": "You are helpul assistant. You are male"},
                   {"role":"user", "content":user_message}]
           
            payload = json.dumps({
                "model": "gpt-3.5-turbo",
                "messages": data,
                "temperature": 0.7
              })
      
            response = requests.post('https://api.openai.com/v1/chat/completions',
                                     headers=headers_for_chatgpt,
                                     data=payload)
      
            print(response)
            if response.ok:
              # check status of ok response success or processing?
              gpt_reply = response.json()
              print(gpt_reply)
              gpt_output_role = gpt_reply['choices'][0]['message']['role']
              gpt_output_content = gpt_reply['choices'][0]['message']['content']
              gpt_output_prompt_tokens = gpt_reply['usage']['prompt_tokens']
              gpt_output_completetion_tokens = gpt_reply['usage']['completion_tokens']
              gpt_output_total_tokens = gpt_reply['usage']['total_tokens']
      
              #record response from gpt to mongodb
              message_gpt = {
                'user_id': event.source.user_id,
                'message': gpt_output_content,
                'timestamp': timestamp,
                'gpt_role': gpt_output_role,
                'gpt_prompt_token': gpt_output_prompt_tokens,
                'gpt_completion_token' : gpt_output_completetion_tokens,
                'gpt_total_tokens' : gpt_output_total_tokens,
                'input_message' : user_message
              }
      
              reply_message = ("🤖OnemaiGPT(Eco🍃) : ") + gpt_output_content
      
              #send reply to user
              line_bot_api.reply_message(event.reply_token,
                                         TextSendMessage(text=reply_message))
    
              #decrease freetoken after complete
              freetoken_left = pull_freetoken - gpt_output_total_tokens
    
              #update freetoken left to user
              filter = {'user_id': event.source.user_id}
              newvalues = {"$set": {'freetoken': freetoken_left}}
              master_users_collection.update_one(filter, newvalues)
      
              #keep chat gpt history chat for counting each user's token #payment
              history_pure_message_gpt_collection.insert_one(message_gpt)
              
            else:
              reply_message = "❗Error ลองพิมพ์ @clearchat เพื่อล้างประวัติการ chat ก่อนนะ! " + str(
                response)
      
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
      display_name = "❗Unknown"

    # Insert the user ID and display name into the master_users collection
    master_users_collection.insert_one({
      'user_id': user_id,
      'display_name': display_name,
      'timestamp': timestamp,
      'main_model': "midjourney",
      'lora_model': "-",
      'controlnet_model0': "-",
      'set_pos': "-",
      'set_neg': "-",
      'autobeauty' : True,
      'emb_model' : "-",
      'upload_creidt': 20
    })

    # Insert the document into the messages collection
  messages_collection.insert_one(message_doc)


def reply_message_to_user(reply_message):
  replytoken = session.get("replytoken")
  line_bot_api.reply_message(replytoken, TextSendMessage(text=reply_message))

def upload_image(file_name, file):
  try:
    #add extension to file name before upload
    file_name = file_name + '.png'

    # Upload the file to Amazon S3
    s3_client.upload_fileobj(file, bucket_name, file_name)

    # Get the URL of the uploaded file
    image_url = f'https://{bucket_name}.s3.amazonaws.com/{file_name}'

    return image_url
  except ClientError as e:
    # Handle any errors that occur during the upload
    print(e)
    return "Error"



if __name__ == '__main__':
  app.run(host='0.0.0.0', port=81)
