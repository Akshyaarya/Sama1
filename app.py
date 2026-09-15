import os
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this-secret-key')

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
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
