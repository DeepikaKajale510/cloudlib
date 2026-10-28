import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st

DB_FILE = "library.db"
LOAN_DAYS = 14
FINE_PER_DAY = 5

st.set_page_config(page_title="CloudLib", page_icon="📚", layout="wide")

st.markdown(
    """
<style>
.hero{background:linear-gradient(135deg,#3b5bdb,#7048e8);color:#fff;padding:22px 26px;
border-radius:18px;margin-bottom:1.1rem;box-shadow:0 10px 30px rgba(59,91,219,.25)}
.hero h1{margin:0;font-size:28px;color:#fff}.hero p{margin:2px 0 0;opacity:.85}
div[data-testid="stMetric"]{background:rgba(128,128,128,.10);border-radius:16px;padding:14px 16px;
box-shadow:0 1px 2px rgba(16,24,40,.06),0 8px 22px rgba(16,24,40,.06)}
.stButton>button,.stFormSubmitButton>button{border-radius:10px;font-weight:600}
</style>
<div class="hero"><h1>📚 CloudLib</h1><p>Smart library management in the cloud</p></div>
""",
    unsafe_allow_html=True,
)


# ---------- database ----------
def conn():
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def run(sql, args=()):
    with conn() as c:
        c.execute(sql, args)


def table(sql, args=()):
    with conn() as c:
        return pd.read_sql_query(sql, c, params=args)


def init_db():
    with conn() as c:
        c.executescript(
            """
            create table if not exists books(id integer primary key autoincrement,
                title text, author text, category text, copies integer);
            create table if not exists members(id integer primary key autoincrement,
                name text, email text);
            create table if not exists loans(id integer primary key autoincrement,
                book_id integer, member_id integer, issued text, due text,
                returned text, fine integer default 0);
            """
        )
        if c.execute("select count(*) from books").fetchone()[0] == 0:
            c.executemany(
                "insert into books(title,author,category,copies) values(?,?,?,?)",
                [
                    ("Introduction to Algorithms", "T. Cormen", "Computer Science", 3),
                    ("Cloud Computing: Concepts, Technology & Architecture", "Thomas Erl", "Cloud", 2),
                    ("Operating System Concepts", "A. Silberschatz", "Computer Science", 2),
                    ("Clean Code", "Robert C. Martin", "Software", 1),
                    ("Wings of Fire", "A. P. J. Abdul Kalam", "Biography", 4),
                ],
            )
            c.executemany(
                "insert into members(name,email) values(?,?)",
                [("Asha Patil", "asha@example.com"), ("Rohan Deshmukh", "rohan@example.com")],
            )


def get_books():
    return table(
        """select b.id, b.title, b.author, b.category, b.copies,
           b.copies - (select count(*) from loans l
                       where l.book_id = b.id and l.returned is null) as available
           from books b order by b.title"""
    )


def get_loans():
    return table(
        """select l.id, b.title as book, m.name as member, l.issued, l.due,
           l.returned, l.fine from loans l
           join books b on b.id = l.book_id join members m on m.id = l.member_id
           order by l.id desc"""
    )


def late_fine(due_text):
    late_days = (date.today() - date.fromisoformat(due_text)).days
    return max(0, late_days) * FINE_PER_DAY


def get_pin():
    try:
        return str(st.secrets.get("LIBRARIAN_PIN", "1234"))
    except Exception:
        return "1234"


def flash(msg):
    st.session_state["flash"] = msg
    st.rerun()


init_db()
st.session_state.setdefault("lib", False)
lib = st.session_state["lib"]

# ---------- sidebar login ----------
with st.sidebar:
    st.header("Account")
    if lib:
        st.success("Logged in as Librarian")
        if st.button("Logout"):
            st.session_state["lib"] = False
            st.rerun()
    else:
        st.info("Reader (read-only)")
        pin = st.text_input("Librarian PIN", type="password")
        if st.button("Login"):
            if pin == get_pin():
                st.session_state["lib"] = True
                st.rerun()
            else:
                st.error("Wrong PIN")

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

books = get_books()
loans = get_loans()
members = table("select * from members order by name")
today = date.today().isoformat()
active = loans[loans["returned"].isna()]
overdue = active[active["due"] < today]

names = ["📊 Dashboard", "📖 Books"]
if lib:
    names += ["👥 Members", "🔄 Issue / Return"]
tabs = st.tabs(names)

# ---------- dashboard ----------
with tabs[0]:
    c = st.columns(5 if lib else 4)
    c[0].metric("Titles", len(books))
    c[1].metric("Total copies", int(books["copies"].sum()))
    c[2].metric("Available", int(books["available"].sum()))
    c[3].metric("Overdue", len(overdue))
    if lib:
        c[4].metric("Fines collected", f"₹{int(loans['fine'].sum())}")
        st.subheader("Overdue books")
        if overdue.empty:
            st.success("Nothing overdue 🎉")
        else:
            od = overdue[["book", "member", "due"]].copy()
            od["fine (₹)"] = overdue["due"].apply(late_fine)
            st.dataframe(od, hide_index=True)
    else:
        st.info("Read-only view. Log in as librarian from the sidebar to manage the library.")

# ---------- books ----------
with tabs[1]:
    search = st.text_input("Search title, author or category", placeholder="Type to search…")
    shown = books
    if search:
        mask = books[["title", "author", "category"]].apply(
            lambda col: col.str.contains(search, case=False, na=False, regex=False)
        ).any(axis=1)
        shown = books[mask]
    st.dataframe(
        shown.rename(columns={"title": "Title", "author": "Author", "category": "Category",
                              "copies": "Copies", "available": "Available"}).drop(columns="id"),
        hide_index=True,
    )
    if lib:
        with st.expander("➕ Add a book"):
            with st.form("add_book", clear_on_submit=True):
                t = st.text_input("Title")
                a = st.text_input("Author")
                cat = st.text_input("Category", value="General")
                n = st.number_input("Copies", min_value=1, value=1)
                if st.form_submit_button("Add book"):
                    if t.strip() and a.strip():
                        run("insert into books(title,author,category,copies) values(?,?,?,?)",
                            (t.strip(), a.strip(), cat.strip() or "General", int(n)))
                        flash("Book added")
                    else:
                        st.error("Title and author are required")
        with st.expander("🗑️ Delete a book"):
            if books.empty:
                st.write("No books.")
            else:
                pick = st.selectbox("Book", books["id"], format_func=lambda i: books.set_index("id").loc[i, "title"])
                if st.button("Delete book"):
                    if (active["book"] == books.set_index("id").loc[pick, "title"]).any():
                        st.error("This book has active loans")
                    else:
                        run("delete from books where id=?", (int(pick),))
                        flash("Book deleted")

if lib:
    # ---------- members ----------
    with tabs[2]:
        st.dataframe(members.rename(columns={"name": "Name", "email": "Email"}).drop(columns="id"),
                     hide_index=True)
        with st.form("add_member", clear_on_submit=True):
            st.subheader("Register member")
            mn = st.text_input("Full name")
            me = st.text_input("Email")
            if st.form_submit_button("Add member"):
                if mn.strip():
                    run("insert into members(name,email) values(?,?)", (mn.strip(), me.strip()))
                    flash("Member added")
                else:
                    st.error("Name is required")
        if not members.empty:
            with st.expander("🗑️ Remove a member"):
                mpick = st.selectbox("Member", members["id"],
                                     format_func=lambda i: members.set_index("id").loc[i, "name"])
                if st.button("Remove member"):
                    name = members.set_index("id").loc[mpick, "name"]
                    if (active["member"] == name).any():
                        st.error("This member has unreturned books")
                    else:
                        run("delete from members where id=?", (int(mpick),))
                        flash("Member removed")

    # ---------- issue / return ----------
    with tabs[3]:
        left, right = st.columns(2)
        with left:
            st.subheader("Issue a book")
            free = books[books["available"] > 0]
            if members.empty or free.empty:
                st.warning("Add members and available books first.")
            else:
                with st.form("issue"):
                    who = st.selectbox("Member", members["id"],
                                       format_func=lambda i: members.set_index("id").loc[i, "name"])
                    what = st.selectbox("Book", free["id"],
                                        format_func=lambda i: f"{free.set_index('id').loc[i, 'title']} "
                                                              f"({free.set_index('id').loc[i, 'available']} left)")
                    if st.form_submit_button("Issue book"):
                        due = (date.today() + timedelta(days=LOAN_DAYS)).isoformat()
                        run("insert into loans(book_id,member_id,issued,due) values(?,?,?,?)",
                            (int(what), int(who), today, due))
                        flash(f"Book issued. Due on {due}")
        with right:
            st.subheader("Return a book")
            if active.empty:
                st.info("No books are currently issued.")
            else:
                with st.form("return"):
                    lid = st.selectbox("Loan", active["id"],
                                       format_func=lambda i: f"{active.set_index('id').loc[i, 'book']} "
                                                             f"→ {active.set_index('id').loc[i, 'member']}")
                    if st.form_submit_button("Return book"):
                        fine = late_fine(active.set_index("id").loc[lid, "due"])
                        run("update loans set returned=?, fine=? where id=?", (today, fine, int(lid)))
                        flash(f"Returned. Fine: ₹{fine}" if fine else "Returned on time")
        st.subheader("Loan records")
        hist = loans.rename(columns={"book": "Book", "member": "Member", "issued": "Issued",
                                     "due": "Due", "returned": "Returned", "fine": "Fine (₹)"}).drop(columns="id")
        st.dataframe(hist, hide_index=True)
