import streamlit as st
from .agent import generate_draft
from .approval_queue import list_queue, approve_item, reject_item
import yaml
from .paths import resource_path

def load_config():
    with open(resource_path("config", "feature_flags.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)

st.title("🟦 MSquared Governed Brand Agent")
st.caption("Human-supervised. Audit-tracked. Draft-first.")

tab1, tab2, tab3 = st.tabs(["Draft Content", "Approval Queue", "Settings"])

with tab1:
    content_type = st.selectbox("Type", ["x_post", "email"])
    input_text = st.text_area("Input / Context")
    if st.button("Generate Draft"):
        draft = generate_draft(content_type, input_text)
        st.success("Draft added to queue")
        st.json(draft)

with tab2:
    queue = list_queue()
    for item in queue:
        st.write(f"**{item['type']}** - {item.get('risk_level')}")
        st.text_area("Draft", item['draft'], key=item['id'])
        col1, col2 = st.columns(2)
        if col1.button("Approve", key=f"app_{item['id']}"):
            approve_item(item['id'])
        if col2.button("Reject", key=f"rej_{item['id']}"):
            reject_item(item['id'])

with tab3:
    st.write("Feature Flags:", load_config())
    st.info("Email: Porkbun IMAP/SMTP for msquared@diiac.io")
    st.info("X: @MSQUARED_2026 via Tweepy")
