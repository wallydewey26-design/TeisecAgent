from flask import session, redirect, url_for, render_template, request
from . import main
from .. import teisecAgent
from ..auth.credentials import validate_passkey, get_permissions
from ..auth.decorators import login_required


@main.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        passkey = request.form.get('passkey', '').strip()
        role = validate_passkey(passkey)
        if role:
            session['role'] = role
            session['permissions'] = get_permissions(role)
            # next destination was stored server-side by login_required; never from user input
            next_path = session.pop('login_next', None) or url_for('main.index')
            return redirect(next_path)
        error = 'Invalid passkey. Please try again.'
    return render_template('login.html', error=error)

@main.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))

@main.route('/', defaults={'sessionId': None}, methods=['GET'])
@main.route('/<sessionId>', methods=['GET'])
@login_required
def index(sessionId):
    if sessionId is None:
        sessionId=teisecAgent.clear_session()
        return redirect(url_for('main.index', sessionId=sessionId))
    return render_template('homepage.html', role=session.get('role'), permissions=session.get('permissions', []))

@main.route('/session/raw/<sessionId>', methods=['GET'])
@login_required
def display_sessio_raw(sessionId):
    session_data = teisecAgent.retrievedsession(sessionId)
    return session_data

@main.route('/sessiontasks/<sessionId>', methods=['GET'])
@login_required
def display_session_details(sessionId):
    session_data = teisecAgent.retrievedsession(sessionId)
    models = {
        "4o-Mini": {
            "input_price_per_million": 0.14392,
            "output_price_per_million": 0.5757
        },
        "4o": {
            "input_price_per_million": 2.39866,
            "output_price_per_million": 9.5747
        }
    }
    total_input_tokens=0
    total_output_tokens=0
    for token in session_data["session_tokens"]:
        total_input_tokens += token["tokens"]["prompt_tokens"]
        total_output_tokens += token["tokens"]["completion_tokens"]
    total_tokens = total_input_tokens + total_output_tokens

    return render_template('sessiondetails.html', tasks=session_data['tasks'], models=models, total_tokens=total_tokens, total_input_tokens=total_input_tokens, total_output_tokens=total_output_tokens)

@main.route('/session/<sessionId>', methods=['GET'])
@login_required
def display_session(sessionId):
    session_data = teisecAgent.retrievedsession(sessionId)
    models = {
        "4o-Mini": {
            "input_price_per_million": 0.14392,
            "output_price_per_million": 0.5757
        },
        "4o": {
            "input_price_per_million": 2.39866,
            "output_price_per_million": 9.5747
        }
    }
    total_input_tokens=0
    total_output_tokens=0
    for token in session_data["session_tokens"]:
        total_input_tokens += token["tokens"]["prompt_tokens"]
        total_output_tokens += token["tokens"]["completion_tokens"]
    total_tokens = total_input_tokens + total_output_tokens

    return render_template('session.html', session=session_data, models=models, total_tokens=total_tokens, total_input_tokens=total_input_tokens, total_output_tokens=total_output_tokens)

