from time import time
from flask import session
from flask_socketio import emit, join_room, leave_room, send, disconnect
from .. import socketio
from .. import teisecAgent

@socketio.on('prompt', namespace='/teisec')  
def run_prompt(message):
    if 'role' not in session:
        disconnect()
        return
    user_prompt=message['user_prompt']
    sessionId=message['sessionId']
    print('Received message: ' + user_prompt) 
    if sessionId is None:
        sessionId=teisecAgent.clear_session() 
        emit('actionmessage',{"action":'NewSession','sessionId':sessionId})
    processed_responses=teisecAgent.run_prompt(sessionId,'html',user_prompt,emit)
    emit('completedmessage',{"message":'Processing Done'})

@socketio.on('clear_session', namespace='/teisec')  
def clear_session(sessionId):
    if 'role' not in session:
        disconnect()
        return
    if session.get('role') not in ('admin', 'owner'):
        emit('debugmessage', {"message": 'Forbidden: insufficient role'})
        return
    print('Received message: Clear Session' )  
    sessionId=teisecAgent.clear_session()
    emit('debugmessage',{"message":'Session cleared'})
    emit('actionmessage',{"action":'NewSession','sessionId':sessionId})