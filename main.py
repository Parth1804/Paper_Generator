import json
import os
import io
import textwrap
from typing import List, Optional
from dotenv import load_dotenv
import streamlit as st
from pydantic import BaseModel, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Frame, Image, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

# Import authentication and database modules
from auth import validate_email, validate_password_strength, validate_username
from database import (
    init_database, register_user, authenticate_user, get_user_info,
    user_exists, email_exists
)
from user_data import UserDataManager

load_dotenv()

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=1.5)

# Initialize database
init_database()


class ProgramQuestion(BaseModel):
    title: str
    description: str
    difficulty: str
    function_signature: str
    examples: List[dict]
    constraints: Optional[str]
    test_cases: List[dict]


class GitQuestion(BaseModel):
    title: str
    prompt: str
    instructions: List[str]
    expected_state: str
    verification: List[str]
    difficulty: str


class GeneratedPaper(BaseModel):
    topic: str
    exam_type: str
    questions: List[dict]


programming_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert problem setter. Return ONLY JSON (no extra text)."),
    ("human",
     "Return ONLY a JSON object with shape: "
     "{{\"topic\": str, \"exam_type\": \"programming\", \"questions\": [" 
     "{{\"title\": str, \"description\": str, \"difficulty\": str, "
     "\"function_signature\": str, \"examples\": [{{\"input\": str, \"output\": str, \"explanation\": str}}], "
     "\"constraints\": str, \"test_cases\": [{{\"input\": str, \"expected_output\": str}}]}}]}}. "
     "Make {num_questions} {difficulty} LeetCode-style programming question(s) for topic '{topic}'. "
     "Examples must include input/output exactly and be runnable for testing. Test cases must be straightforward to check. "
     "Do NOT add any commentary, only return the JSON object."
    )
])

git_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert instructor for git/github tasks. Return ONLY JSON (no extra text)."),
    ("human",
     "Return ONLY a JSON object with shape: "
     "{{\"topic\": str, \"exam_type\": \"git\", \"questions\": ["
     "{{\"title\": str, \"prompt\": str, \"difficulty\": str, "
     "\"instructions\": [str], \"expected_state\": str, \"verification\": [str]}}]}}. "
     "Make {num_questions} {difficulty} git/github exercises for topic '{topic}'. "
     "IMPORTANT: For each exercise include STEP-BY-STEP INSTRUCTIONS written in plain English describing WHAT the trainee should do to achieve the goal — "
     "do NOT include exact shell or git commands. For example: 'Create a new branch named feature-X, make changes to file foo.py and commit them' (natural-language only). "
     "Provide verification steps also in plain language (e.g., 'Check that the new branch exists and contains your commit'). "
     "Do NOT include literal command lines like 'git add', 'git commit', 'git push', or any other shell commands. "
     "Do NOT add commentary, return only the JSON."
    )
])


def extract_json_from_text(text: str) -> dict:
    """Strip fences and find first JSON object."""
    if text is None:
        raise ValueError("Empty model response")
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`\n ")
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("Could not parse JSON from model output")


def validate_and_build(p: dict) -> GeneratedPaper:
    try:
        paper = GeneratedPaper(**p)
    except ValidationError as e:
        raise ValueError(f"Invalid paper format: {e}")

    if paper.exam_type == "programming":
        validated_qs = []
        for q in paper.questions:
            validated_qs.append(ProgramQuestion(**q).dict())
        paper.questions = validated_qs
    elif paper.exam_type == "git":
        validated_qs = []
        for q in paper.questions:
            validated_qs.append(GitQuestion(**q).dict())
        paper.questions = validated_qs
    else:
        raise ValueError("Unknown exam_type")
    return paper


def format_testcase_leetcode(tc) -> str:
    if isinstance(tc, dict):
        if "input" in tc and isinstance(tc["input"], str):
            inp = tc["input"].strip()
            parts = [p.strip() for p in inp.split(",") if p.strip()]
            lines = []
            if parts and any("=" in p for p in parts):
                for p in parts:
                    lines.append(p)
            else:
                lines.append(inp)
            if "expected_output" in tc:
                lines.append(f"Expected Output: {repr(tc['expected_output'])}")
            return "\n".join(lines)
        else:
            lines = []
            for k, v in tc.items():
                if k in ("expected_output", "output", "answer"):
                    continue
                try:
                    val_str = json.dumps(v, ensure_ascii=False)
                    if isinstance(v, str):
                        val_str = f'"{v}"'
                except Exception:
                    val_str = str(v)
                lines.append(f"{k} = {val_str}")
            expected = None
            for key in ("expected_output", "output", "answer"):
                if key in tc:
                    expected = tc[key]
                    break
            if expected is not None:
                lines.append(f"Expected Output: {repr(expected)}")
            return "\n".join(lines)
    if isinstance(tc, str):
        return tc
    try:
        return json.dumps(tc, ensure_ascii=False)
    except Exception:
        return str(tc)


def build_paper_pdf_bytes(paper: dict, title: Optional[str] = None) -> bytes:
    buffer = io.BytesIO()
    page_width, page_height = A4

    left_margin = 22 * mm
    right_margin = 22 * mm
    top_margin = 20 * mm
    bottom_margin = 20 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )

    base_styles = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            spaceAfter=12,
            alignment=0,  # left
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            spaceBefore=4,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base_styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=11,
            textColor=colors.grey,
            spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base_styles["Code"],
            fontName="Courier",
            fontSize=9,
            leading=12,
            backColor=colors.whitesmoke,
            leftIndent=6,
            rightIndent=6,
            spaceBefore=4,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
            textColor=colors.grey,
        ),
    }

    def _header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        header_text_left = title or paper.get("topic", "")
        header_text_right = (paper.get("exam_type", "") or "").upper()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(colors.HexColor("#444444"))
        canvas_obj.drawString(left_margin, page_height - 15 * mm, header_text_left)
        canvas_obj.drawRightString(page_width - right_margin, page_height - 15 * mm, header_text_right)

        page_num_text = f"Page {doc_obj.page}"
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawCentredString(page_width / 2.0, 12 * mm, page_num_text)
        canvas_obj.restoreState()

    flowables = []

    display_title = title or paper.get("topic", "Paper")
    flowables.append(Paragraph(display_title + f" — { (paper.get('exam_type','')).upper() }", styles["title"]))

    meta_data = [
        ["Topic:", paper.get("topic", "")],
        ["Exam type:", paper.get("exam_type", "")],
        ["Questions:", str(len(paper.get("questions", [])))],
    ]
    meta_tbl = Table(meta_data, colWidths=[60 * mm, (page_width - left_margin - right_margin - 60 * mm)])
    meta_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    flowables.append(meta_tbl)
    flowables.append(Spacer(1, 6))

    flowables.append(Paragraph("Generated paper — review the questions below.", styles["meta"]))
    flowables.append(Spacer(1, 8))

    for idx, q in enumerate(paper.get("questions", []), start=1):
        q_title = f"{idx}. {q.get('title', 'Untitled')}"
        flowables.append(Paragraph(q_title, styles["heading"]))

        if paper.get("exam_type") == "programming":
            flowables.append(Paragraph(q.get("description", ""), styles["body"]))
            func_line = f"<b>Difficulty:</b> {q.get('difficulty','')} &nbsp;&mdash;&nbsp; <b>Function:</b> {q.get('function_signature','')}"
            flowables.append(Paragraph(func_line, styles["small"]))
            flowables.append(Spacer(1, 4))

            exs = q.get("examples", []) or []
            if exs:
                flowables.append(Paragraph("<b>Examples</b>", styles["body"]))
                for ex in exs:
                    ex_text = f"<b>Input:</b> {ex.get('input','')}<br/><b>Output:</b> {ex.get('output','')}"
                    if ex.get("explanation"):
                        ex_text += f"<br/><i>{ex.get('explanation')}</i>"
                    flowables.append(Paragraph(ex_text, styles["code"]))

            tcs = q.get("test_cases", []) or []
            if tcs:
                flowables.append(Paragraph("<b>Test cases</b>", styles["body"]))
                for tc in tcs:
                    tc_text = format_testcase_leetcode(tc)
                    tc_text_html = tc_text.replace("\n", "<br/>")
                    flowables.append(Paragraph(tc_text_html, styles["code"]))

        else:
            flowables.append(Paragraph(q.get("prompt", ""), styles["body"]))
            flowables.append(Spacer(1, 4))
            ins = q.get("instructions", []) or []
            if ins:
                flowables.append(Paragraph("<b>Instructions</b>", styles["body"]))
                for step in ins:
                    flowables.append(Paragraph(f"• {step}", styles["body"]))
                flowables.append(Spacer(1, 6))

        flowables.append(Spacer(1, 10))

    doc.build(flowables, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer.read()


st.set_page_config(page_title="Training Exam Generator", layout="wide")
st.title("Training Exam / Paper Generator")

# Initialize authentication state
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
    st.session_state['user_id'] = None
    st.session_state['username'] = None
    st.session_state['page'] = 'login'

if 'topics' not in st.session_state:
    st.session_state['topics'] = []

if 'papers' not in st.session_state:
    st.session_state['papers'] = {}

# Authentication UI
def show_login_page():
    """Display login page."""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("🔐 Login")
        
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Login", use_container_width=True):
                if not username or not password:
                    st.error("Please enter username and password")
                else:
                    success, user_id, message = authenticate_user(username, password)
                    if success:
                        st.session_state['user_id'] = user_id
                        st.session_state['username'] = username
                        st.session_state['authenticated'] = True
                        st.session_state['page'] = 'app'
                        st.success(f"Welcome back, {username}!")
                        
                        # Load user data
                        st.session_state['topics'] = UserDataManager.load_topics(user_id)
                        st.session_state['papers'] = UserDataManager.load_papers(user_id)
                        
                        st.rerun()
                    else:
                        st.error(message)
        
        with col_b:
            if st.button("Create Account", use_container_width=True):
                st.session_state['page'] = 'signup'
                st.rerun()
        
        st.markdown("---")
        


def show_signup_page():
    """Display signup page."""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("📝 Create Account")
        
        username = st.text_input("Username", key="signup_username", help="3-20 characters, letters/numbers/underscore")
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password", 
                                help="Min 8 chars, 1 uppercase, 1 lowercase, 1 digit")
        confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
        
        if st.button("Sign Up", use_container_width=True):
            # Validation
            if not all([username, email, password, confirm_password]):
                st.error("All fields are required")
            elif password != confirm_password:
                st.error("Passwords do not match")
            else:
                # Validate username
                valid_user, msg = validate_username(username)
                if not valid_user:
                    st.error(msg)
                else:
                    # Validate email
                    if not validate_email(email):
                        st.error("Invalid email format")
                    else:
                        # Validate password
                        valid_pwd, msg = validate_password_strength(password)
                        if not valid_pwd:
                            st.error(msg)
                        else:
                            # Register user
                            success, message = register_user(username, email, password)
                            if success:
                                st.success(message)
                                st.info("✅ Account created! Please login with your credentials.")
                                st.session_state['page'] = 'login'
                                st.rerun()
                            else:
                                st.error(message)
        
        st.markdown("---")
        col_back, _ = st.columns([1, 3])
        with col_back:
            if st.button("← Back to Login", use_container_width=True):
                st.session_state['page'] = 'login'
                st.rerun()


# Main app page routing
if not st.session_state['authenticated']:
    if st.session_state['page'] == 'signup':
        show_signup_page()
    else:
        show_login_page()
else:
    # User info in sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state['username']}")
        user_info = get_user_info(st.session_state['user_id'])
        if user_info:
            st.caption(f"📧 {user_info['email']}")
        
        st.markdown("---")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state['authenticated'] = False
            st.session_state['user_id'] = None
            st.session_state['username'] = None
            st.session_state['topics'] = []
            st.session_state['papers'] = {}
            st.session_state['page'] = 'login'
            st.success("Logged out successfully")
            st.rerun()
    
    # Main app content
    with st.form("add_topic_form", clear_on_submit=True):
        new_topic = st.text_input("Add new learning topic (Programming Language | Git/GitHub)")
        submitted = st.form_submit_button("Add Topic")
        if submitted:
            if new_topic.strip():
                topic_data = {"title": new_topic.strip()}
                st.session_state["topics"].insert(0, topic_data)
                # Save to database
                UserDataManager.add_topic(st.session_state['user_id'], new_topic.strip())
                st.success(f"Added topic: {new_topic.strip()}")
            else:
                st.warning("Enter a non-empty topic.")

st.markdown("---")

for idx, t in enumerate(st.session_state["topics"]):
    col1, col2, col3 = st.columns([6, 2, 2])
    with col1:
        st.subheader(f"{t['title']}")
    with col2:
        if st.button("Create Paper", key=f"create_{idx}"):
            st.session_state["_create_for"] = idx
    with col3:
        if st.button("Remove", key=f"remove_{idx}"):
            removed_topic = st.session_state["topics"].pop(idx)
            # Delete from database (use topic title as key)
            if '_key' in removed_topic:
                UserDataManager.delete_topic(st.session_state['user_id'], removed_topic['_key'])
            st.rerun()

if st.session_state.get("_create_for", None) is not None:
    sel_idx = st.session_state["_create_for"]
    if sel_idx < 0 or sel_idx >= len(st.session_state["topics"]):
        del st.session_state["_create_for"]
        st.rerun()
    topic_obj = st.session_state["topics"][sel_idx]
    st.markdown("### Create Paper for: " + topic_obj["title"])
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        exam_type = st.selectbox("Exam Type", ["programming", "git"])
    with col_b:
        difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"])
    with col_c:
        num_questions = st.text_input("Number of questions", "1")

    if st.button("Generate Paper Now"):
        if exam_type == "programming":
            prompt = programming_prompt
        else:
            prompt = git_prompt
        chain = prompt | model
        try:
            with st.spinner("Generating paper — this may take a few seconds..."):
                response = chain.invoke(
                    {
                        "topic": topic_obj["title"],
                        "num_questions": num_questions,
                        "difficulty": difficulty,
                    }
                )
                raw = response.content if hasattr(response, "content") else response
                raw_text = raw if isinstance(raw, str) else json.dumps(raw)
                parsed = extract_json_from_text(raw_text)
                paper = validate_and_build(parsed)
                paper_dict = paper.dict()
                st.session_state.setdefault("papers", {})[topic_obj["title"]] = paper_dict
                # Save to database
                UserDataManager.save_paper(st.session_state['user_id'], topic_obj["title"], paper_dict)
                st.success("Paper generated successfully!")
                del st.session_state["_create_for"]
        except Exception as e:
            st.error(f"Failed to generate paper: {e}")

st.markdown("---")

papers = st.session_state.get("papers", {})
if papers:
    st.header("Generated Papers")
    for topic_name, paper in list(papers.items()):
        exp_title = f"{topic_name}  —  {paper.get('exam_type','').upper()}"
        with st.expander(exp_title, expanded=False):
            header_col_left, header_col_right = st.columns([18, 1])
            with header_col_right:
                if st.button("🗑️", key=f"delete_{topic_name}"):
                    if topic_name in st.session_state.get("papers", {}):
                        del st.session_state["papers"][topic_name]
                        # Delete from database
                        UserDataManager.delete_paper(st.session_state['user_id'], topic_name)
                    st.rerun()
            with header_col_left:
                st.markdown(f"**Topic:** {paper.get('topic','')}")
                st.markdown(f"**Questions:** {len(paper.get('questions', []))}")
            st.markdown("---")
            for i, q in enumerate(paper["questions"], start=1):
                st.markdown(f"**Q{i}. {q.get('title', 'Untitled')}**")
                if paper["exam_type"] == "programming":
                    st.markdown(q["description"])
                    st.markdown(f"- Difficulty: {q['difficulty']}")
                    st.markdown(f"- Function signature: `{q['function_signature']}`")
                    st.markdown("- Examples:")
                    for ex in q["examples"]:
                        st.markdown(f"  - Input: `{ex['input']}` → Output: `{ex['output']}` ({ex.get('explanation','')})")
                    st.markdown("- Test cases:")
                    for tc in q["test_cases"]:
                        formatted = format_testcase_leetcode(tc)
                        st.code(formatted)
                else:
                    st.markdown(q.get("prompt", ""))
                    ins = q.get("instructions", []) or []
                    for step in ins:
                        st.markdown(f"• {step}")
                st.markdown("---")

            try:
                pdf_bytes = build_paper_pdf_bytes(paper, title=topic_name) 
                st.download_button(
                    label="Download paper as PDF",
                    data=pdf_bytes,
                    file_name=f"{topic_name.replace(' ', '_')}_paper.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Failed to build PDF: {e}")

    st.markdown("---")
    st.markdown("<p style='text-align: center;'>© 2025 Training Exam Generator</p>", unsafe_allow_html=True)
