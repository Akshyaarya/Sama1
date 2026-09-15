import os
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import check_password_hash

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this-secret-key')

# Self-contained web UI: templates/CSS are embedded so GitHub's browser uploader does not need folders.
from jinja2 import DictLoader
TEMPLATES = {
    'base.html': '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sama Cafe</title><link rel="stylesheet" href="{{ url_for(\'static\',filename=\'style.css\') }}"></head><body><header><div class="brand">☕ Sama Cafe <small>Created by Amit</small></div>{% if current_user %}<div class="user">{{current_user.display_name}} · {{current_user.role}} · <a href="{{url_for(\'logout\')}}">Logout</a></div>{% endif %}</header>{% if current_user %}<nav><a href="{{url_for(\'dashboard\')}}">Dashboard</a><a href="{{url_for(\'new_bill\')}}">New Bill</a><a href="{{url_for(\'bills\')}}">Bills</a><a href="{{url_for(\'stock\')}}">Stock</a><a href="{{url_for(\'customers\')}}">Customers</a><a href="{{url_for(\'pending\')}}">Pending</a><a href="{{url_for(\'reports\')}}">Reports</a>{% if current_user.role==\'admin\' %}<a href="{{url_for(\'staff\')}}">Staff Permissions</a>{% endif %}</nav>{% endif %}<main>{% with msgs=get_flashed_messages(with_categories=true) %}{% for cat,msg in msgs %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}{% block content %}{% endblock %}</main><footer>Sama Cafe · Online billing & stock</footer></body></html>\n',
    'bill_view.html': '{% extends \'base.html\' %}{% block content %}<div class="toolbar"><h1>Bill #{{bill.bill_no}}</h1><button onclick="window.print()" class="btn">🖨 Print</button>{% if bill.customer_mobile %}<a class="btn" target="_blank" href="https://wa.me/{{bill.customer_mobile}}?text={{(\'Sama Cafe Bill #\'+bill.bill_no|string+\'%0A\'+(bill.customer_name or \'\')+\'%0ATotal: ₹\'+(\'%.2f\'|format(bill.total or 0))+\'%0APaid: ₹\'+(\'%.2f\'|format(bill.paid or 0))+\'%0APending: ₹\'+(\'%.2f\'|format(bill.pending or 0)))|urlencode}}">WhatsApp</a>{% endif %}</div><div class="billprint"><h2>Sama Cafe</h2><p>Created by Amit</p><p>Bill #{{bill.bill_no}} · {{bill.bill_date}}</p><p>{{bill.customer_name or \'Walk-in Customer\'}}</p><table><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th></tr>{% for x in items %}<tr><td>{{x.item_name}}</td><td>{{x.quantity}}</td><td>₹{{\'%.2f\'|format(x.rate or 0)}}</td><td>₹{{\'%.2f\'|format(x.amount or 0)}}</td></tr>{% endfor %}</table><hr><p>Discount: ₹{{\'%.2f\'|format(bill.discount or 0)}}</p><h2>Total: ₹{{\'%.2f\'|format(bill.total or 0)}}</h2><p>Paid: ₹{{\'%.2f\'|format(bill.paid or 0)}} · Pending: ₹{{\'%.2f\'|format(bill.pending or 0)}}</p><p>Payment: {{bill.payment_mode}}</p><p>Thank you! ☕ Visit Again</p></div>{% endblock %}\n',
    'bills.html': '{% extends \'base.html\' %}{% block content %}<div class="toolbar"><h1>Bills</h1><a class="btn" href="{{url_for(\'new_bill\')}}">+ New Bill</a><form><input name="q" value="{{q}}" placeholder="Search bill/customer"><button>Search</button></form></div><table><tr><th>Bill</th><th>Date</th><th>Customer</th><th>Total</th><th>Paid</th><th>Pending</th><th>Mode</th><th></th></tr>{% for r in rows %}<tr><td>#{{r.bill_no}}</td><td>{{r.bill_date}}</td><td>{{r.customer_name or \'-\'}}</td><td>₹{{\'%.2f\'|format(r.total or 0)}}</td><td>₹{{\'%.2f\'|format(r.paid or 0)}}</td><td>₹{{\'%.2f\'|format(r.pending or 0)}}</td><td>{{r.payment_mode}}</td><td><a href="{{url_for(\'bill_view\',bill_no=r.bill_no)}}">View</a></td></tr>{% endfor %}</table>{% endblock %}\n',
    'customers.html': "{% extends 'base.html' %}{% block content %}<h1>Customers</h1><table><tr><th>ID</th><th>Name</th><th>Mobile</th></tr>{% for r in rows %}<tr><td>{{r.id}}</td><td>{{r.name}}</td><td>{{r.mobile}}</td></tr>{% endfor %}</table>{% endblock %}\n",
    'dashboard.html': '{% extends \'base.html\' %}{% block content %}<h1>Dashboard</h1><div class="cards"><div><b>{{stats.bills}}</b><span>Total Bills</span></div><div><b>{{stats.today_bills}}</b><span>Today Bills</span></div><div><b>{{stats.customers}}</b><span>Customers</span></div><div><b>{{stats.stock_items}}</b><span>Stock Items</span></div></div><div class="grid"><section class="panel"><h2>Recent Bills</h2><table><tr><th>Bill</th><th>Date</th><th>Customer</th><th>Total</th><th>Pending</th></tr>{% for r in recent %}<tr><td><a href="{{url_for(\'bill_view\',bill_no=r.bill_no)}}">#{{r.bill_no}}</a></td><td>{{r.bill_date}}</td><td>{{r.customer_name or \'-\'}}</td><td>₹{{\'%.2f\'|format(r.total or 0)}}</td><td>₹{{\'%.2f\'|format(r.pending or 0)}}</td></tr>{% endfor %}</table></section><section class="panel"><h2>Current Stock</h2><table><tr><th>Item</th><th>Qty</th><th>Rate</th></tr>{% for r in stock %}<tr><td>{{r.item_name}}</td><td>{{r.quantity}}</td><td>₹{{\'%.2f\'|format(r.rate or 0)}}</td></tr>{% endfor %}</table></section></div>{% endblock %}\n',
    'login.html': '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sama Cafe Login</title><link rel="stylesheet" href="{{url_for(\'static\',filename=\'style.css\')}}"></head><body class="login"><div class="loginbox"><div class="logo">☕</div><h1>Sama Cafe</h1><p>Created by Amit</p><form method="post"><input name="username" placeholder="Username" required autofocus><input name="password" type="password" placeholder="Password" required><button>Login</button></form></div></body></html>\n',
    'new_bill.html': '{% extends \'base.html\' %}{% block content %}<h1>New Bill</h1><form method="post" id="billform"><div class="formgrid"><label>Bill No<input name="bill_no" value="{{next_bill}}" required></label><label>Customer<input name="customer_name"></label><label>WhatsApp Mobile<input name="customer_mobile" placeholder="10 digit mobile"></label><label>Payment Mode<select name="payment_mode"><option>Cash</option><option>Online</option><option>Paytm</option><option>Credit</option></select></label><label>Paid<input id="paid" name="paid" type="number" step="0.01" value="0"></label><label>Discount<input id="discount" name="discount" type="number" step="0.01" value="0"></label><label>Discount Reason<input name="discount_reason"></label><label>UTR Number<input name="utr_number"></label></div><h2>Items</h2><table id="items"><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th><th></th></tr><tr class="itemrow"><td><select name="item_name[]" class="item">{% for x in items %}<option value="{{x.item_name}}" data-rate="{{x.rate}}">{{x.item_name}} (stock {{x.quantity}})</option>{% endfor %}</select></td><td><input name="qty[]" class="qty" type="number" step="0.01" value="1"></td><td><input name="rate[]" class="rate" type="number" step="0.01" value="0"></td><td class="amount">0.00</td><td><button type="button" onclick="this.closest(\'tr\').remove();calc()">×</button></td></tr></table><button type="button" class="secondary" onclick="addRow()">+ Add Item</button><div class="totalbox">Subtotal ₹<span id="sub">0.00</span> · Discount ₹<span id="disc">0.00</span> · <b>Total ₹<span id="total">0.00</span></b></div><button class="btn">Save Bill</button></form><script>function bind(r){let s=r.querySelector(\'.item\'),rate=r.querySelector(\'.rate\');s.onchange=()=>{rate.value=s.options[s.selectedIndex].dataset.rate||0;calc()};r.querySelector(\'.qty\').oninput=calc;rate.oninput=calc;rate.value=s.options[s.selectedIndex].dataset.rate||0}function calc(){let sub=0;document.querySelectorAll(\'.itemrow\').forEach(r=>{let a=(+r.querySelector(\'.qty\').value||0)*(+r.querySelector(\'.rate\').value||0);r.querySelector(\'.amount\').textContent=a.toFixed(2);sub+=a});let d=+document.getElementById(\'discount\').value||0;document.getElementById(\'sub\').textContent=sub.toFixed(2);document.getElementById(\'disc\').textContent=d.toFixed(2);document.getElementById(\'total\').textContent=Math.max(0,sub-d).toFixed(2)}document.getElementById(\'discount\').oninput=calc;bind(document.querySelector(\'.itemrow\'));calc();function addRow(){let r=document.querySelector(\'.itemrow\').cloneNode(true);r.querySelector(\'.qty\').value=1;document.getElementById(\'items\').appendChild(r);bind(r);calc()}</script>{% endblock %}\n',
    'pending.html': "{% extends 'base.html' %}{% block content %}<h1>Pending Payments</h1><table><tr><th>Bill</th><th>Date</th><th>Customer</th><th>Total</th><th>Paid</th><th>Pending</th></tr>{% for r in rows %}<tr><td>#{{r.bill_no}}</td><td>{{r.bill_date}}</td><td>{{r.customer_name}}</td><td>₹{{'%.2f'|format(r.total or 0)}}</td><td>₹{{'%.2f'|format(r.paid or 0)}}</td><td><b>₹{{'%.2f'|format(r.pending or 0)}}</b></td></tr>{% endfor %}</table>{% endblock %}\n",
    'reports.html': '{% extends \'base.html\' %}{% block content %}<h1>Sales Report</h1><div class="cards"><div><b>₹{{\'%.2f\'|format(total)}}</b><span>Total Sales</span></div><div><b>₹{{\'%.2f\'|format(paid)}}</b><span>Paid</span></div><div><b>₹{{\'%.2f\'|format(pending)}}</b><span>Pending</span></div></div><table><tr><th>Bill</th><th>Date</th><th>Customer</th><th>Total</th><th>Paid</th><th>Pending</th></tr>{% for r in rows %}<tr><td>#{{r.bill_no}}</td><td>{{r.bill_date}}</td><td>{{r.customer_name}}</td><td>₹{{\'%.2f\'|format(r.total or 0)}}</td><td>₹{{\'%.2f\'|format(r.paid or 0)}}</td><td>₹{{\'%.2f\'|format(r.pending or 0)}}</td></tr>{% endfor %}</table>{% endblock %}\n',
    'staff.html': '{% extends \'base.html\' %}{% block content %}<h1>Staff Permissions</h1><table><tr><th>User</th><th>Display Name</th><th>Role</th><th>Active</th></tr>{% for u in users %}<tr><td>{{u.username}}</td><td>{{u.display_name}}</td><td>{{u.role}}</td><td>{{u.active}}</td></tr>{% endfor %}</table><h2>Permission Update</h2><form method="post" action="{{url_for(\'staff_permission\')}}" class="formgrid"><label>Username<select name="username">{% for u in users if u.role!=\'admin\' %}<option>{{u.username}}</option>{% endfor %}</select></label><label>Permission<select name="permission">{% for k,v in permissions.items() %}<option value="{{k}}">{{v}}</option>{% endfor %}</select></label><label>Allowed<select name="allowed"><option value="1">Yes</option><option value="0">No</option></select></label><button class="btn">Save Permission</button></form>{% endblock %}\n',
    'stock.html': '{% extends \'base.html\' %}{% block content %}<h1>Stock</h1><div class="panel"><h2>Add New Stock</h2><form method="post" action="{{url_for(\'receive_stock\')}}" class="formgrid"><label>Item<select name="item_name">{% for x in rows %}<option>{{x.item_name}}</option>{% endfor %}</select></label><label>Quantity<input name="quantity" type="number" step="0.01" required></label><label>Purchase Rate<input name="rate" type="number" step="0.01"></label><label>Invoice No<input name="invoice_no"></label><label>Invoice Date<input name="invoice_date" placeholder="DD-MM-YYYY"></label><label>Note<input name="note"></label><button class="btn">Save Stock</button></form></div><table><tr><th>Item</th><th>Opening</th><th>Current Qty</th><th>Rate</th></tr>{% for r in rows %}<tr><td>{{r.item_name}}</td><td>{{r.opening_qty}}</td><td>{{r.quantity}}</td><td>₹{{\'%.2f\'|format(r.rate or 0)}}</td></tr>{% endfor %}</table><h2>Recent Receipts</h2><table><tr><th>Date</th><th>Item</th><th>Qty</th><th>Rate</th><th>Invoice</th></tr>{% for r in receipts %}<tr><td>{{r.received_date}}</td><td>{{r.item_name}}</td><td>{{r.quantity}}</td><td>₹{{\'%.2f\'|format(r.rate or 0)}}</td><td>{{r.invoice_no or \'-\'}}</td></tr>{% endfor %}</table>{% endblock %}\n',
}
app.jinja_loader = DictLoader(TEMPLATES)
STYLE_CSS = '*{box-sizing:border-box}body{margin:0;font-family:Arial,Segoe UI,sans-serif;background:#f5f7fb;color:#172033}header{background:#111827;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:3}.brand{font-size:22px;font-weight:800}.brand small{font-size:12px;color:#93c5fd;margin-left:8px}.user{font-size:14px}.user a{color:#fff;margin-left:12px}nav{display:flex;gap:6px;flex-wrap:wrap;padding:10px 20px;background:#fff;border-bottom:1px solid #e5e7eb}nav a{padding:9px 12px;text-decoration:none;color:#1f2937;border-radius:8px}nav a:hover{background:#e5e7eb}main{max-width:1450px;margin:auto;padding:24px}h1{margin-top:0}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-bottom:22px}.cards>div,.panel{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:18px;box-shadow:0 3px 14px #00000008}.cards b{display:block;font-size:28px}.cards span{color:#64748b}.grid{display:grid;grid-template-columns:1.5fr 1fr;gap:18px}.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:15px}.toolbar h1{margin-right:auto}.toolbar form{display:flex;gap:7px}table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden}th,td{padding:10px 12px;border-bottom:1px solid #edf0f4;text-align:left}th{background:#eef2ff}a{color:#2563eb}.btn,button{background:#2563eb;color:#fff;border:0;padding:10px 14px;border-radius:8px;text-decoration:none;cursor:pointer;font-weight:700}.secondary{background:#475569}.formgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;align-items:end}.formgrid label{display:flex;flex-direction:column;gap:6px;font-weight:700;font-size:13px}.formgrid input,.formgrid select,input,select{padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff}.flash{padding:12px 15px;border-radius:10px;margin-bottom:14px}.success{background:#dcfce7;color:#166534}.danger{background:#fee2e2;color:#991b1b}.totalbox{background:#fff;padding:18px;margin:18px 0;font-size:18px;text-align:right}.billprint{background:#fff;max-width:720px;padding:25px;margin:auto;border:1px solid #ddd}.login{display:grid;place-items:center;min-height:100vh;background:#111827}.loginbox{background:#fff;width:min(420px,92vw);padding:35px;border-radius:18px;text-align:center}.logo{font-size:45px}.loginbox input,.loginbox button{width:100%;margin:7px 0;padding:13px}.loginbox h1{margin-bottom:4px}footer{text-align:center;padding:25px;color:#64748b}@media(max-width:900px){.cards{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.formgrid{grid-template-columns:1fr 1fr}table{font-size:13px}main{padding:14px;overflow-x:auto}}@media print{header,nav,footer,.toolbar{display:none!important}main{padding:0}.billprint{border:0;box-shadow:none;max-width:none}}\n'

@app.get('/static/<path:filename>', endpoint='static')
def style_static(filename):
    if filename != 'style.css':
        return Response('Not Found', status=404)
    return Response(STYLE_CSS, mimetype='text/css')

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
# Accept either the project URL or a copied Data API URL; normalize to the project root.
if SUPABASE_URL.endswith('/rest/v1'):
    SUPABASE_URL = SUPABASE_URL[:-8].rstrip('/')
if SUPABASE_URL.endswith('/rest/v1/'):
    SUPABASE_URL = SUPABASE_URL[:-9].rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_SECRET_KEY', '')

# Uses Supabase in production. SQLite fallback is included only for local testing.
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    DB_MODE = 'supabase'
else:
    import sqlite3
    DB_MODE = 'sqlite'
    SQLITE_PATH = os.getenv('SQLITE_PATH', os.path.join(os.path.dirname(__file__), 'Sama_Cafe_LIVE.db'))

PERMS = {
    'new_bill':'New Billing','stock':'Stock / Opening / Closing / New Stock','damage':'Stock Damage',
    'customers':'Customers','monthly_customers':'Monthly Customers','pending':'Pending Payments',
    'sales_report':'Sales Report / Export','expense':'Expense / Daily Cash','bill_history':'Bill History / Reports',
    'edit_bill':'Edit Bills','delete_bill':'Delete Bills','print_bill':'Print Bills','whatsapp':'WhatsApp Bills'
}
DEFAULT_STAFF_PERMISSIONS = {'new_bill','pending','print_bill','whatsapp'}

TABLES = ['bills','bill_items','customers','customer_payments','monthly_customers','stock','stock_receipts','stock_damage','stock_day_opening','stock_day_override','users','user_permissions','expenses','cash_day','bill_edit_log','stock_edit_log']


def sql_rows(table, columns='*', filters=None, order=None, limit=None):
    if DB_MODE == 'supabase':
        q = db.table(table).select(columns)
        for key, value in (filters or {}).items():
            if value is not None and value != '': q = q.eq(key, value)
        if order: q = q.order(order[0], desc=order[1])
        if limit: q = q.limit(limit)
        return q.execute().data or []
    con = sqlite3.connect(SQLITE_PATH); con.row_factory=sqlite3.Row
    q = f'SELECT {columns} FROM {table}'; vals=[]
    if filters:
        parts=[]
        for k,v in filters.items():
            if v is not None and v!='': parts.append(f'"{k}"=?'); vals.append(v)
        if parts: q += ' WHERE ' + ' AND '.join(parts)
    if order: q += f' ORDER BY {order[0]} {"DESC" if order[1] else "ASC"}'
    if limit: q += f' LIMIT {int(limit)}'
    rows=[dict(r) for r in con.execute(q,vals).fetchall()]; con.close(); return rows


def sql_count(table, filters=None):
    if DB_MODE == 'supabase':
        q=db.table(table).select('*', count='exact', head=True)
        for k,v in (filters or {}).items():
            if v is not None and v!='': q=q.eq(k,v)
        return q.execute().count or 0
    con=sqlite3.connect(SQLITE_PATH); vals=[]; q=f'SELECT COUNT(*) FROM {table}'
    if filters:
        parts=[]
        for k,v in filters.items():
            if v is not None and v!='': parts.append(f'"{k}"=?'); vals.append(v)
        if parts:q+=' WHERE '+' AND '.join(parts)
    n=con.execute(q,vals).fetchone()[0]; con.close(); return n


def insert_row(table, data):
    if DB_MODE == 'supabase': return db.table(table).insert(data).execute().data
    con=sqlite3.connect(SQLITE_PATH); cols=', '.join(data); marks=', '.join('?' for _ in data)
    con.execute(f'INSERT INTO {table} ({cols}) VALUES ({marks})', list(data.values())); con.commit(); con.close(); return [data]


def update_rows(table, data, filters):
    if DB_MODE == 'supabase':
        q=db.table(table).update(data)
        for k,v in filters.items(): q=q.eq(k,v)
        return q.execute().data
    con=sqlite3.connect(SQLITE_PATH); sets=', '.join(f'{k}=?' for k in data); vals=list(data.values()); wh=' AND '.join(f'{k}=?' for k in filters); vals += list(filters.values())
    con.execute(f'UPDATE {table} SET {sets} WHERE {wh}', vals); con.commit(); con.close(); return []


def delete_rows(table, filters):
    if DB_MODE == 'supabase':
        q=db.table(table).delete()
        for k,v in filters.items(): q=q.eq(k,v)
        return q.execute().data
    con=sqlite3.connect(SQLITE_PATH); wh=' AND '.join(f'{k}=?' for k in filters); con.execute(f'DELETE FROM {table} WHERE {wh}', list(filters.values())); con.commit(); con.close()


def current_user(): return session.get('user')


def login_required(f):
    @wraps(f)
    def w(*a,**kw):
        if not current_user(): return redirect(url_for('login'))
        return f(*a,**kw)
    return w


def has_perm(p):
    u=current_user()
    if not u: return False
    if u.get('role')=='admin': return True
    rows=sql_rows('user_permissions','allowed',{'username':u['username'],'permission':p},limit=1)
    return bool(rows and rows[0].get('allowed'))


def perm_required(p):
    def deco(f):
        @wraps(f)
        def w(*a,**kw):
            if not has_perm(p):
                flash(f"Permission denied: {PERMS.get(p,p)}", 'danger'); return redirect(request.referrer or url_for('dashboard'))
            return f(*a,**kw)
        return w
    return deco

@app.context_processor
def inject():
    return {'current_user':current_user(),'PERMS':PERMS,'db_mode':DB_MODE}

@app.get('/health')
def health(): return {'ok':True,'database':DB_MODE}

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username=request.form.get('username','').strip(); password=request.form.get('password','')
        rows=sql_rows('users','id,username,password,display_name,role,active',{'username':username},limit=1)
        if rows and rows[0].get('active',1):
            stored=rows[0].get('password','')
            ok = check_password_hash(stored,password) if stored.startswith(('pbkdf2:','scrypt:')) else stored==password
            if ok:
                session['user']={k:rows[0].get(k) for k in ('username','display_name','role')}
                return redirect(url_for('dashboard'))
        flash('Username ya password galat hai.','danger')
    return render_template('login.html')

@app.get('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.get('/')
@login_required
def dashboard():
    today=date.today().isoformat()
    stats={
        'bills':sql_count('bills'),
        'today_bills':sql_count('bills',{'bill_date':today}),
        'customers':sql_count('customers'),
        'stock_items':sql_count('stock')
    }
    recent=sql_rows('bills','bill_no,customer_name,bill_date,total,paid,pending,payment_mode,billed_by',order=('bill_no',True),limit=12)
    stock=sql_rows('stock','item_name,rate,quantity,opening_qty',order=('item_name',False),limit=100)
    return render_template('dashboard.html',stats=stats,recent=recent,stock=stock)

@app.route('/bills', methods=['GET','POST'])
@login_required
@perm_required('bill_history')
def bills():
    q=request.args.get('q','').strip(); rows=sql_rows('bills','*',order=('bill_no',True),limit=500)
    if q:
        ql=q.lower(); rows=[r for r in rows if ql in str(r.get('bill_no','')).lower() or ql in str(r.get('customer_name','')).lower()]
    return render_template('bills.html',rows=rows,q=q)

@app.route('/bill/new', methods=['GET','POST'])
@login_required
@perm_required('new_bill')
def new_bill():
    items=sql_rows('stock','item_name,rate,quantity',order=('item_name',False),limit=500)
    if request.method=='POST':
        try:
            bill_no=int(request.form['bill_no']); customer=request.form.get('customer_name','').strip(); mobile=request.form.get('customer_mobile','').strip()
            mode=request.form.get('payment_mode','Cash'); paid=float(request.form.get('paid') or 0); discount=float(request.form.get('discount') or 0)
            names=request.form.getlist('item_name[]'); qtys=request.form.getlist('qty[]'); rates=request.form.getlist('rate[]')
            bill_items=[]; total=0
            requested={}
            for n,q,r in zip(names,qtys,rates):
                if not n: continue
                q=float(q); r=float(r); requested[n]=requested.get(n,0)+q; bill_items.append((n,q,r,q*r)); total += q*r
            total=max(0,total-discount); pending=max(0,total-paid)
            if not bill_items: raise ValueError('Kam se kam 1 item select karein.')
            for n,q in requested.items():
                sr=sql_rows('stock','quantity',{'item_name':n},limit=1)
                available=float(sr[0]['quantity']) if sr else 0
                if q>available: raise ValueError(f'{n}: stock sirf {available:g} hai.')
            now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            insert_row('bills',{'bill_no':bill_no,'customer_name':customer,'bill_date':now,'total':total,'payment_mode':mode,'paid':paid,'pending':pending,'billed_by':current_user()['display_name'],'customer_mobile':mobile,'discount':discount,'discount_reason':request.form.get('discount_reason',''),'last_edited_by':'','last_edited_at':'','payment_date':now,'utr_number':request.form.get('utr_number',''),'paid_via':request.form.get('paid_via',mode)})
            for n,q,r,a in bill_items:
                insert_row('bill_items',{'bill_no':bill_no,'item_name':n,'quantity':q,'rate':r,'amount':a})
                sr=sql_rows('stock','quantity',{'item_name':n},limit=1); newq=float(sr[0]['quantity'])-q
                update_rows('stock',{'quantity':newq},{'item_name':n})
            if customer:
                existing=sql_rows('customers','id,name,mobile',{'name':customer},limit=1)
                if not existing: insert_row('customers',{'name':customer,'mobile':mobile})
                elif mobile: update_rows('customers',{'mobile':mobile},{'name':customer})
            flash(f'Bill #{bill_no} save ho gaya.','success'); return redirect(url_for('bill_view',bill_no=bill_no))
        except Exception as e:
            flash(str(e),'danger')
    maxno=(sql_rows('bills','bill_no',order=('bill_no',True),limit=1) or [{'bill_no':0}])[0]['bill_no']
    return render_template('new_bill.html',items=items,next_bill=int(maxno)+1)

@app.get('/bill/<int:bill_no>')
@login_required
def bill_view(bill_no):
    bill=sql_rows('bills','*',{'bill_no':bill_no},limit=1)
    if not bill: flash('Bill not found','danger'); return redirect(url_for('bills'))
    its=sql_rows('bill_items','*',{'bill_no':bill_no},order=('id',False),limit=500)
    return render_template('bill_view.html',bill=bill[0],items=its)

@app.get('/stock')
@login_required
@perm_required('stock')
def stock():
    rows=sql_rows('stock','*',order=('item_name',False),limit=500)
    receipts=sql_rows('stock_receipts','*',order=('id',True),limit=30)
    return render_template('stock.html',rows=rows,receipts=receipts)

@app.post('/stock/receive')
@login_required
@perm_required('stock')
def receive_stock():
    name=request.form.get('item_name','').strip(); qty=float(request.form.get('quantity') or 0); rate=float(request.form.get('rate') or 0)
    row=sql_rows('stock','quantity',{'item_name':name},limit=1)
    if not row: flash('Item nahi mila. Pehle stock item add karein.','danger')
    elif qty<=0: flash('Quantity valid honi chahiye.','danger')
    else:
        update_rows('stock',{'quantity':float(row[0]['quantity'])+qty,'rate':rate},{'item_name':name})
        insert_row('stock_receipts',{'item_name':name,'quantity':qty,'rate':rate,'received_date':date.today().strftime('%d-%m-%Y'),'note':request.form.get('note',''),'invoice_no':request.form.get('invoice_no',''),'invoice_date':request.form.get('invoice_date','')})
        flash('New stock save ho gaya.','success')
    return redirect(url_for('stock'))

@app.get('/customers')
@login_required
@perm_required('customers')
def customers():
    rows=sql_rows('customers','*',order=('name',False),limit=500); return render_template('customers.html',rows=rows)

@app.get('/pending')
@login_required
@perm_required('pending')
def pending():
    rows=sql_rows('bills','bill_no,customer_name,bill_date,total,paid,pending',order=('bill_no',True),limit=500)
    rows=[r for r in rows if float(r.get('pending') or 0)>0]
    return render_template('pending.html',rows=rows)

@app.get('/staff')
@login_required
def staff():
    if current_user()['role']!='admin': flash('Admin only','danger'); return redirect(url_for('dashboard'))
    users=sql_rows('users','id,username,display_name,role,active',order=('id',False),limit=100)
    return render_template('staff.html',users=users,permissions=PERMS)

@app.post('/staff/permission')
@login_required
def staff_permission():
    if current_user()['role']!='admin': return redirect(url_for('dashboard'))
    username=request.form['username']; perm=request.form['permission']; allowed=1 if request.form.get('allowed')=='1' else 0
    rows=sql_rows('user_permissions','id',{'username':username,'permission':perm},limit=1)
    if rows: update_rows('user_permissions',{'allowed':allowed},{'username':username,'permission':perm})
    else: insert_row('user_permissions',{'username':username,'permission':perm,'allowed':allowed})
    return redirect(url_for('staff'))

@app.get('/reports')
@login_required
@perm_required('sales_report')
def reports():
    rows=sql_rows('bills','bill_no,bill_date,customer_name,total,paid,pending,payment_mode,billed_by',order=('bill_no',True),limit=1000)
    total=sum(float(r.get('total') or 0) for r in rows); paid=sum(float(r.get('paid') or 0) for r in rows); pending_total=sum(float(r.get('pending') or 0) for r in rows)
    return render_template('reports.html',rows=rows,total=total,paid=paid,pending=pending_total)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=False)
