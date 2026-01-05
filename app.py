import os
import re
import random
import string
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DecimalField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Load environment variables from .env file
load_dotenv()

# --- APP CONFIGURATION ---

# Explicitly tell Flask where to find the 'static' folder
app = Flask(__name__, static_folder='static')

# Secret key for session management and CSRF protection
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_secure_random_secret_key_for_dev')
# Database configuration (SQLite for simplicity)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bank.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- LOCAL EMAIL CONFIGURATION FOR TESTING ---
# This setup sends emails to a local debugging server instead of a real one.
# Run this command in a separate terminal: python -m smtpd -c DebuggingServer -n localhost:8025
app.config['MAIL_SERVER'] = 'localhost'
app.config['MAIL_PORT'] = 8025
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = None # No username needed for local server
app.config['MAIL_PASSWORD'] = None # No password needed for local server
app.config['MAIL_DEFAULT_SENDER'] = ('Bank of Japan', 'noreply@boj.com')


# --- INITIALIZE EXTENSIONS ---

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Redirect to login page if user is not authenticated
login_manager.login_message_category = 'info'
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# --- LANGCHAIN SETUP ---
# Ensure you have OPENAI_API_KEY in your .env file
llm = ChatOpenAI(model="gpt-3.5-turbo")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful bank assistant for the Bank of Japan. Answer the user's questions about general banking topics. Do not provide financial advice or perform any real transactions."),
    ("user", "{input}")
])
output_parser = StrOutputParser()
chain = prompt | llm | output_parser

# --- CONTEXT PROCESSOR ---

@app.context_processor
def inject_now():
    """Injects the current UTC time into all templates."""
    return {'now': datetime.now(timezone.utc)}

# --- DATABASE MODELS ---

class User(UserMixin, db.Model):
    """User model for storing user details."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    is_employee = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    account = db.relationship('Account', backref='owner', uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

class Account(db.Model):
    """Account model for storing bank account details."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    balance = db.Column(db.Float, nullable=False, default=1000.00) # New users get a starting balance
    transactions = db.relationship('Transaction', backref='account', lazy=True)

    def __repr__(self):
        return f"Account('{self.account_number}', Balance: {self.balance})"

class Transaction(db.Model):
    """Transaction model for storing transaction history."""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False) # 'credit' or 'debit'
    description = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"Transaction('{self.type}', Amount: {self.amount}, On: {self.timestamp})"

# --- USER LOADER ---

@login_manager.user_loader
def load_user(user_id):
    """Loads user from the database for Flask-Login."""
    return User.query.get(int(user_id))

# --- CUSTOM DECORATORS ---

def employee_required(f):
    """Decorator to restrict access to employees only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_employee:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- HELPER FUNCTIONS ---

def generate_username():
    """Generates a unique username like 'BOJ123456'."""
    while True:
        username = 'BOJ' + ''.join(random.choices(string.digits, k=6))
        if not User.query.filter_by(username=username).first():
            return username

def generate_account_number():
    """Generates a unique 10-digit account number."""
    while True:
        account_number = ''.join(random.choices(string.digits, k=10))
        if not Account.query.filter_by(account_number=account_number).first():
            return account_number

def send_email(recipient, subject, template, **kwargs):
    """Sends an email. Returns True on success, or the error message on failure."""
    try:
        msg = Message(subject, recipients=[recipient])
        msg.html = render_template(template, **kwargs)
        mail.send(msg)
        return True
    except Exception as e:
        # Return the actual error message for debugging
        return str(e)

# --- FORMS ---

def validate_password(form, field):
    """Custom validator for password complexity."""
    password = field.data
    if not re.search(r'[A-Z]', password):
        raise ValidationError('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', password):
        raise ValidationError('Password must contain at least one lowercase letter.')
    if not re.search(r'\d', password):
        raise ValidationError('Password must contain at least one digit.')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError('Password must contain at least one special character.')

def validate_email_domain(form, field):
    """Custom validator to allow only specific email domains."""
    allowed_domains = ['gmail.com', 'yahoo.com'] # Add more allowed domains here
    email = field.data.lower()
    domain = email.split('@')[-1]
    
    if domain not in allowed_domains and not domain.endswith('.in'):
        raise ValidationError('Only specific email domains are allowed (e.g., gmail.com, yahoo.com, or .in addresses).')

class RegistrationForm(FlaskForm):
    """Form for user registration."""
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email(), validate_email_domain])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=15)])
    address = StringField('Address', validators=[DataRequired(), Length(min=5, max=200)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8), validate_password])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already taken. Please choose a different one.')

class LoginForm(FlaskForm):
    """Form for user login."""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ForgotPasswordForm(FlaskForm):
    """Form to request a password reset email."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class ResetPasswordForm(FlaskForm):
    """Form to reset password."""
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8), validate_password])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

class TransferForm(FlaskForm):
    """Form for transferring money."""
    recipient_account_number = StringField('Recipient Account Number', validators=[DataRequired(), Length(min=10, max=10)])
    amount = DecimalField('Amount', validators=[DataRequired()])
    submit = SubmitField('Transfer')

    def validate_amount(self, amount):
        if amount.data <= 0:
            raise ValidationError('Transfer amount must be positive.')
        if amount.data > current_user.account.balance:
            raise ValidationError('Insufficient funds.')

class DepositForm(FlaskForm):
    """Form for admin to deposit money."""
    account_number = StringField('Account Number', validators=[DataRequired(), Length(min=10, max=10)])
    amount = DecimalField('Amount', validators=[DataRequired()])
    submit = SubmitField('Deposit')

    def validate_amount(self, amount):
        if amount.data <= 0:
            raise ValidationError('Deposit amount must be positive.')

class AdminTransferForm(FlaskForm):
    """Form for admin to transfer money between any two accounts."""
    sender_account_number = StringField('Sender Account Number', validators=[DataRequired(), Length(min=10, max=10)])
    recipient_account_number = StringField('Recipient Account Number', validators=[DataRequired(), Length(min=10, max=10)])
    amount = DecimalField('Amount', validators=[DataRequired()])
    submit = SubmitField('Transfer')

    def validate_amount(self, amount):
        if amount.data <= 0:
            raise ValidationError('Transfer amount must be positive.')

# --- ROUTES ---

@app.route("/")
def index():
    """Homepage: Redirects to dashboard if logged in, otherwise shows login/register page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# =========================
# 🔴 NEW ROUTE (ADDED)
# ALB HEALTH CHECK KE LIYE
# =========================
@app.route("/health")
def health():
    return "OK", 200   # <-- YE LINE ADD KI HAI

# --- Authentication Routes ---

@app.route("/register", methods=['GET', 'POST'])
def register():
    """Handles user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        username = generate_username()
        user = User(
            username=username,
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            address=form.address.data,
            password_hash=hashed_password
        )
        db.session.add(user)
        db.session.commit() # Commit to get the user ID for the account

        account = Account(
            owner=user,
            account_number=generate_account_number(),
            balance=1000.00 # Initial bonus
        )
        db.session.add(account)
        db.session.commit()

        # Send welcome email and check for errors
        email_result = send_email(
            user.email,
            'Welcome to Bank of Japan!',
            'emails/welcome_email.html',
            name=user.name,
            username=user.username
        )

        if email_result is True:
            flash(f'Account created for {form.name.data}! Your username is {username}. Email sent to local debug server.', 'success')
        else:
            flash(f'Account created, but email failed. Your username is {username}.', 'warning')
            flash(f'Email Error: {email_result}', 'danger')

        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=True)
            flash('You have been logged in!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
def logout():
    """Logs the user out."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route("/forgot-password", methods=['GET', 'POST'])
def forgot_password():
    """Handles forgot password request."""
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = s.dumps(user.email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            email_result = send_email(
                user.email,
                'Password Reset Request',
                'emails/reset_email.html',
                name=user.name,
                reset_url=reset_url
            )
            if email_result is True:
                flash('Password reset instructions sent to local debug server.', 'info')
            else:
                flash(f'Failed to send email. Error: {email_result}', 'danger')
        else:
            flash('Email address not found.', 'warning')
        return redirect(url_for('login'))
    return render_template('forgot_password.html', title='Forgot Password', form=form)

@app.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_password(token):
    """Handles password reset with a token."""
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=3600) # Token expires in 1 hour
    except SignatureExpired:
        flash('The password reset link is expired.', 'danger')
        return redirect(url_for('forgot_password'))
    except Exception:
        flash('The password reset link is invalid.', 'danger')
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=email).first()
        if user:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user.password_hash = hashed_password
            db.session.commit()
            flash('Your password has been updated! You are now able to log in.', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html', title='Reset Password', form=form)


# --- User Dashboard Routes ---

@app.route("/dashboard")
@login_required
def dashboard():
    """Displays user dashboard with account info and recent transactions."""
    account = current_user.account
    recent_transactions = Transaction.query.filter_by(account_id=account.id).order_by(Transaction.timestamp.desc()).limit(5).all()
    return render_template('dashboard.html', title='Dashboard', account=account, transactions=recent_transactions)

@app.route("/transfer", methods=['GET', 'POST'])
@login_required
def transfer():
    """Handles money transfer between accounts."""
    form = TransferForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        recipient_account_number = form.recipient_account_number.data
        sender_account = current_user.account

        if sender_account.account_number == recipient_account_number:
            flash('You cannot transfer money to your own account.', 'danger')
            return redirect(url_for('transfer'))

        recipient_account = Account.query.filter_by(account_number=recipient_account_number).first()

        if not recipient_account:
            flash('Recipient account not found.', 'danger')
            return redirect(url_for('transfer'))

        if sender_account.balance < amount:
            flash('Insufficient funds.', 'danger')
            return redirect(url_for('transfer'))

        sender_account.balance -= amount
        recipient_account.balance += amount

        debit_transaction = Transaction(
            account_id=sender_account.id,
            amount=amount,
            type='debit',
            description=f'Transfer to {recipient_account.owner.name} ({recipient_account.account_number})'
        )
        credit_transaction = Transaction(
            account_id=recipient_account.id,
            amount=amount,
            type='credit',
            description=f'Transfer from {sender_account.owner.name} ({sender_account.account_number})'
        )

        db.session.add(debit_transaction)
        db.session.add(credit_transaction)
        db.session.commit()

        flash(f'Successfully transferred ${amount:.2f} to {recipient_account.owner.name}.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('transfer.html', title='Transfer Money', form=form)

@app.route("/history")
@login_required
def history():
    """Displays paginated transaction history."""
    page = request.args.get('page', 1, type=int)
    transactions = Transaction.query.filter_by(account_id=current_user.account.id)\
        .order_by(Transaction.timestamp.desc())\
        .paginate(page=page, per_page=10)
    return render_template('history.html', title='Transaction History', transactions=transactions)


# --- Admin Routes ---

@app.route("/admin")
@login_required
@employee_required
def admin_dashboard():
    """Admin dashboard to view all users."""
    search_query = request.args.get('search', '')
    if search_query:
        search_term = f"%{search_query}%"
        users = User.query.filter(
            (User.name.ilike(search_term)) | (User.username.ilike(search_term))
        ).all()
    else:
        users = User.query.all()
    return render_template('admin_dashboard.html', title='Admin Panel', users=users, search_query=search_query)


@app.route("/admin/deposit", methods=['GET', 'POST'])
@login_required
@employee_required
def deposit():
    """Admin functionality to deposit money into a user's account."""
    form = DepositForm()
    if form.validate_on_submit():
        account_number = form.account_number.data
        amount = float(form.amount.data)
        account = Account.query.filter_by(account_number=account_number).first()

        if not account:
            flash('Account not found.', 'danger')
            return redirect(url_for('deposit'))

        account.balance += amount
        deposit_transaction = Transaction(
            account_id=account.id,
            amount=amount,
            type='credit',
            description=f'Deposit by Admin {current_user.name}'
        )
        db.session.add(deposit_transaction)
        db.session.commit()

        flash(f'Successfully deposited ${amount:.2f} into account {account_number}.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('deposit.html', title='Deposit Money', form=form)

@app.route("/admin/user/<int:user_id>")
@login_required
@employee_required
def admin_user_details(user_id):
    """Displays full details and transaction history for a specific user."""
    user = User.query.get_or_404(user_id)
    page = request.args.get('page', 1, type=int)
    transactions = Transaction.query.filter_by(account_id=user.account.id)\
        .order_by(Transaction.timestamp.desc())\
        .paginate(page=page, per_page=10)
    return render_template('admin_user_details.html', title=f'Details for {user.name}', user=user, transactions=transactions)

@app.route("/admin/transfer", methods=['GET', 'POST'])
@login_required
@employee_required
def admin_transfer():
    """Admin functionality to transfer money between any two accounts."""
    form = AdminTransferForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        sender_account_number = form.sender_account_number.data
        recipient_account_number = form.recipient_account_number.data

        if sender_account_number == recipient_account_number:
            flash('Sender and recipient accounts cannot be the same.', 'danger')
            return redirect(url_for('admin_transfer'))

        sender_account = Account.query.filter_by(account_number=sender_account_number).first()
        recipient_account = Account.query.filter_by(account_number=recipient_account_number).first()

        if not sender_account:
            flash(f'Sender account {sender_account_number} not found.', 'danger')
            return redirect(url_for('admin_transfer'))
        
        if not recipient_account:
            flash(f'Recipient account {recipient_account_number} not found.', 'danger')
            return redirect(url_for('admin_transfer'))

        if sender_account.balance < amount:
            flash(f'Insufficient funds in sender account. Current balance: ${sender_account.balance:.2f}', 'danger')
            return redirect(url_for('admin_transfer'))
        
        sender_account.balance -= amount
        recipient_account.balance += amount

        debit_transaction = Transaction(
            account_id=sender_account.id,
            amount=amount,
            type='debit',
            description=f'Admin transfer to {recipient_account.owner.name} ({recipient_account.account_number})'
        )
        credit_transaction = Transaction(
            account_id=recipient_account.id,
            amount=amount,
            type='credit',
            description=f'Transfer from {sender_account.owner.name} ({sender_account.account_number})'
        )

        db.session.add(debit_transaction)
        db.session.add(credit_transaction)
        db.session.commit()

        flash(f'Successfully transferred ${amount:.2f} from {sender_account.owner.name} to {recipient_account.owner.name}.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_transfer.html', title='Admin Transfer', form=form)

# --- CHATBOT ROUTE ---

@app.route("/chat", methods=['POST'])
def chat():
    """Handles chatbot interaction. No login required."""
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        # Get response from LangChain
        ai_response = chain.invoke({"input": user_message})
        return jsonify({'response': ai_response})
    except Exception as e:
        print(f"Chatbot error: {e}")
        return jsonify({'error': 'Sorry, I am having trouble connecting to the AI service.'}), 500

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(is_employee=True).first():
            print("Creating default admin user...")
            hashed_password = bcrypt.generate_password_hash('AdminPass123!').decode('utf-8')
            admin_user = User(
                username='BOJADMIN',
                name='Admin Employee',
                email='admin@boj.com',
                phone='0000000000',
                address='1 Bank Street, Tokyo',
                password_hash=hashed_password,
                is_employee=True
            )
            db.session.add(admin_user)
            db.session.commit()

            admin_account = Account(
                owner=admin_user,
                account_number=generate_account_number(),
                balance=1000000.00
            )
            db.session.add(admin_account)
            db.session.commit()
            print("Admin user 'BOJADMIN' with password 'AdminPass123!' created.")

    app.run(host="0.0.0.0", port=5000, debug=True)

