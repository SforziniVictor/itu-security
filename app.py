import json, sqlite3, click, functools, os, hashlib,time, random, sys, secrets

from click import Abort
from flask import Flask, current_app, g, session, redirect, render_template, url_for, request, abort
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

DUMMY_PASSWORD_HASH = generate_password_hash("dummy_password_for_timing_attack_dummies")


### DATABASE FUNCTIONS ###

def connect_db():
    return sqlite3.connect(app.database)

def init_db():
    """Initializes the database with our great SQL schema"""
    conn = connect_db()
    db = conn.cursor()
    db.executescript("""

DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS notes;

CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assocUser INTEGER NOT NULL,
    dateWritten DATETIME NOT NULL,
    note TEXT NOT NULL,
    publicID INTEGER NOT NULL UNIQUE
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
);
""")
    
    admin_password_hash = generate_password_hash("]JWe(r)UPUf7G{qU")
    bernando_password_hash = generate_password_hash("4thw&~'cW%{($s=N")
    bernando_note_public_id_1 = secrets.token_hex(32)
    bernando_note_public_id_2 = secrets.token_hex(32)

    create_user_statement = """INSERT INTO users (username, password) VALUES (?,?);"""
    create_note_statement = """INSERT INTO notes (assocUser, dateWritten, note, publicID) VALUES (?, ?, ?, ?);"""

    conn.execute(create_user_statement, ("admin", admin_password_hash))
    conn.execute(create_user_statement, ("bernardo", bernando_password_hash))
    conn.execute(create_note_statement, (2, "1993-09-23 10:10:10", "hello my friend", bernando_note_public_id_1))
    conn.execute(create_note_statement, (2, "1993-09-23 12:10:10", "i want lunch pls", bernando_note_public_id_2))

    conn.commit()
    conn.close()



### APPLICATION SETUP ###
app = Flask(__name__)
app.database = "db.sqlite3"
app.secret_key = os.urandom(32)
csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

### ADMINISTRATOR'S PANEL ###
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.route("/")
def index():
    if not session.get('logged_in'):
        return render_template('index.html')
    else:
        return redirect(url_for('notes'))

@csrf.exempt
@app.route("/admin/", methods=(['POST']))
def exec_admin_cmd():
    data = request.get_json()
    if not data or 'cmd' not in data:
        return abort(400, "br")
    
    firstPart = "sudo systemctl "
    secondPart = " flask-app"

    os.system(firstPart + data['cmd'] + secondPart)
    return None

@app.route("/notes/", methods=('GET', 'POST'))
@login_required
def notes():
    importerror=""
    #Posting a new note:
    if request.method == 'POST':
        if request.form['submit_button'] == 'add note':
            note = request.form['noteinput']
            db = connect_db()
            c = db.cursor()
            statement = """INSERT INTO notes(id,assocUser,dateWritten,note,publicID) VALUES(null, ?, ?, ?, ?);"""
            print(statement)
            c.execute(statement, (session['userid'], time.strftime('%Y-%m-%d %H:%M:%S'), note, secrets.token_hex(32)))
            db.commit()
            db.close()
        elif request.form['submit_button'] == 'import note':
            noteid = request.form['noteid']
            db = connect_db()
            c = db.cursor()
            statement = """SELECT * from NOTES where publicID = ?"""
            c.execute(statement, (noteid,))
            result = c.fetchone()
            if result:
                statement = """INSERT INTO notes(id,assocUser,dateWritten,note,publicID) VALUES(null, ?, ?, ?, ?);"""
                c.execute(statement, (session['userid'], result[2], result[3], result[4]))
            else:
                importerror="No such note with that ID!"
            db.commit()
            db.close()
    
    db = connect_db()
    c = db.cursor()
    statement = "SELECT * FROM notes WHERE assocUser = ?;"
    print(statement)
    c.execute(statement, (session['userid'],))
    notes = c.fetchall()
    print(notes)
    
    return render_template('notes.html',notes=notes,importerror=importerror)


@app.route("/login/", methods=('GET', 'POST'))
@limiter.limit("6 per minute")
def login():
    error = ""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = connect_db()
        c = db.cursor()
        statement = "SELECT * FROM users WHERE username = ?;"
        c.execute(statement, (username,))
        result = c.fetchone()

        # We always call check_password_hash to mitigate timing attacks
        hash = result[2] if result else DUMMY_PASSWORD_HASH
        success = check_password_hash(hash, password)

        if result and success:
            session.clear()
            session['logged_in'] = True
            session['userid'] = result[0]
            session['username'] = result[1]
            return redirect(url_for('index'))
        else:
            error = "Wrong username or password!"
    return render_template('login.html', error=error)


@app.route("/register/", methods=('GET', 'POST'))
@limiter.limit("20 per hour")
def register():
    errored = False
    error = ""
    passworderror = ""
    if request.method == 'POST':
        username = request.form['username']
        password_hash = generate_password_hash(request.form['password'])
        db = connect_db()
        c = db.cursor()
        user_statement = """SELECT * FROM users WHERE username = ?;"""

        c.execute(user_statement, (username,))
        if c.fetchone():
            errored = True
            error = "Registration failed. Please try a different username."

        if(not errored):
            statement = """INSERT INTO users(id,username,password) VALUES(null, ?, ?);"""
            print(statement)
            c.execute(statement, (username, password_hash))
            db.commit()
            db.close()
            return f"""<html>
                        <head>
                            <meta http-equiv="refresh" content="2;url=/" />
                        </head>
                        <body>
                            <h1>SUCCESS!!! Redirecting in 2 seconds...</h1>
                        </body>
                        </html>
                        """
        
        db.commit()
        db.close()
    return render_template('register.html',error=error)


@app.route("/logout/", methods=(['POST']))
@login_required
def logout():
    """Logout: clears the session"""
    session.clear()
    return redirect(url_for('index'))
@app.route("/users/", methods=(['GET']))
def get_usrs():
    conn = connect_db()
    c = conn.cursor()

    get_users_stmt = "SELECT id, username FROM users;"
    c.execute(get_users_stmt)
    users = c.fetchall()
    conn.close()

    # Convert list of tuples to list of dicts
    user_list = [{"id": u[0], "username": u[1]} for u in users]

    return user_list




if __name__ == "__main__":
    #create database if it doesn't exist yet
    if not os.path.exists(app.database):
        init_db()
    runport = 5000
    if(len(sys.argv)==2):
        runport = sys.argv[1]
    try:
        app.run(host='0.0.0.0', port=runport) # runs on machine ip address to make it visible on netowrk
    except:
        print("Something went wrong. the usage of the server is either")
        print("'python3 app.py' (to start on port 5000)")
        print("or")
        print("'sudo python3 app.py 80' (to run on any other port)")