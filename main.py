from ast import IsNot
import sys
import os
sys.path.append("vendor")
import json
import uvicorn
import asyncio

from fastapi import Request, FastAPI
from nerualpha.neru import Neru
from nerualpha.providers.voice.voice import Voice
from nerualpha.providers.voice.contracts.vapiEventParams import VapiEventParams
from nerualpha.providers.messages.messages import Messages
from nerualpha.providers.messages.contracts.messageContact import MessageContact
from nerualpha.providers.messages.contracts.smsMessage import SMSMessage
from nerualpha.providers.state.state import State

app = FastAPI()
neru = Neru()

if os.getenv('NERU_CONFIGURATIONS') is None:
    print("NERU_CONFIGURATIONS environment variable is not set")
    sys.exit(1)

contact = json.loads(os.getenv('NERU_CONFIGURATIONS'))['contact']
vonageContact = MessageContact()
vonageContact.type_ = contact['type']
vonageContact.number = contact['number']

async def setupListeners():
    try:
        session = neru.createSession()
        voice = Voice(session)
        await voice.onVapiAnswer('onCall').execute()
    except Exception as e:
        print(e)
        sys.exit(1)

@app.get('/_/health')
async def health():
    return 'OK'

@app.post('/onCall')
async def onCall(request: Request):
    session = neru.createSession()
    voice = Voice(session)
    messages = Messages(session)

    body = await request.json()

    fromContact = MessageContact()
    fromContact.type_ = vonageContact.type_
    fromContact.number = body['from']

    await messages.onMessage('onMessage', fromContact, vonageContact).execute()

    vapiEventParams = VapiEventParams()
    vapiEventParams.callback = 'onEvent'
    vapiEventParams.vapiUUID = body['uuid']

    await voice.onVapiEvent(vapiEventParams).execute()

    return  [
                {
                    'action': 'talk',
                    'text': 'Say some words, then text this number for a transcript'
                },
                {
                    'action': 'input',
                    'type': ['speech']
                }
        ]

@app.post('/onEvent')
async def onEvent(request: Request):
    body = await request.json()
    if 'speech' in body:
        session = neru.getSessionFromRequest(request)
        state = State(session, session.id)
        text = body['speech']['results'][0]['text']
        await state.set('text', text)
    else:
        print(body)
    return 'OK'

@app.post('/onMessage')
async def onMessages(request: Request):
    session = neru.getSessionFromRequest(request)
    messages = Messages(session)
    state = State(session, session.id)

    body = await request.json()
    text = await state.get('text')

    fromNumber = body['from']

    message = SMSMessage()
    message.to = fromNumber
    message.from_ = vonageContact.number
    message.channel = vonageContact.type_
    message.message_type = 'text'
    message.text = f"You said: {text}"

    await messages.send(message).execute()
    return 'OK'


if __name__ == "__main__":
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.run_until_complete(setupListeners())
    port = int(os.getenv('NERU_APP_PORT'))
    uvicorn.run(app, host="0.0.0.0", port=port)