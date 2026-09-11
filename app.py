import streamlit as st
import fitz  # PyMuPDF
import base64
import json
import requests

st.set_page_config(page_title="PalmWood Mortgages - AI Underwriter", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #111111; color: #FFFFFF; }
    h1, h2, h3 { color: #FF8C00 !important; font-family: 'Playfair Display', serif; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 4px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("PalmWood Mortgages")
st.caption("AI-Powered UAE DBR & Pre-Underwriting Engine")

# Load API key safely from Streamlit Secrets
api_key = st.secrets.get("OPENROUTER_API_KEY")

uploaded_file = st.file_uploader("Upload Client Bank Statement (PDF)", type=["pdf"])

if uploaded_file and api_key:
    st.info("Extracting and compressing pages for AI Vision analysis...")
    
    # Render PDF pages as lighter-weight images to prevent timeouts
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    base64_images = []
    
    # Limit to first 3 pages to ensure fast, stable processing
    for page in doc[:3]:
        pix = page.get_pixmap(dpi=100)
        img_data = pix.tobytes("jpeg")
        base64_images.append(base64.b64encode(img_data).decode('utf-8'))
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://palmwood-mortgages.streamlit.app",
        "X-Title": "PalmWood Underwriter"
    }
    
    messages_payload = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": """You are an expert UAE Mortgage Underwriter. Analyze these bank statement pages.
                    Extract the following figures strictly and compute the values:
                    1. Net Monthly Salary (average of recurring monthly payroll credits).
                    2. Existing Monthly Liabilities (Sum of all active Loan EMIs, Mortgages, Car Loans).
                    3. Total Credit Card Limits (Sum of all credit limits found across cards).
                    
                    Return ONLY a raw JSON object with NO extra text or markdown formatting:
                    {
                        "monthly_salary": number,
                        "existing_emis": number,
                        "credit_card_limits": number,
                        "salary_confidence": "HIGH/MEDIUM/LOW",
                        "detected_bank": "string"
                    }"""
                }
            ]
        }
    ]
    
    for b64_img in base64_images:
        messages_payload[0]["content"].append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
        })

    try:
        # Call Vision AI Model with a 30-second timeout guard
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps({
                "model": "openai/gpt-4o-mini",
                "messages": messages_payload
            }),
            timeout=30
        )
        
        if response.status_code == 200:
            res_data = response.json()
            raw_content = res_data['choices'][0]['message']['content'].strip()
            
            if raw_content.startswith("```json"):
                raw_content = raw_content[7:-3].strip()
            elif raw_content.startswith("```"):
                raw_content = raw_content[3:-3].strip()
                
            parsed = json.loads(raw_content)
            
            salary = parsed.get("monthly_salary", 0)
            emis = parsed.get("existing_emis", 0)
            cards = parsed.get("credit_card_limits", 0)
            
            card_liability = cards * 0.05  # UAE 5% CC Rule
            total_debts = emis + card_liability
            dbr = (total_debts / salary * 100) if salary > 0 else 0
            max_emi_capacity = (salary * 0.50) - total_debts
            
            st.success(f"Bank Detected: {parsed.get('detected_bank', 'Unknown')}")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Average Monthly Salary", f"AED {salary:,.2f}")
            col2.metric("Total Monthly Liabilities", f"AED {total_debts:,.2f}")
            
            if dbr <= 50:
                col3.metric("DBR Status", f"{dbr:.1f}%", delta="PASS (<= 50%)", delta_color="normal")
            else:
                col3.metric("DBR Status", f"{dbr:.1f}%", delta="FAIL (> 50%)", delta_color="inverse")
                
            st.markdown("---")
            st.subheader("Underwriting Capacity Summary")
            st.write(f"**Available Monthly EMI Capacity:** AED {max_emi_capacity:,.2f}")
            
        else:
            st.error(f"API Error Code {response.status_code}: Please check your API key or token limits.")
            
    except requests.exceptions.Timeout:
        st.error("The request timed out because the PDF took too long to analyze. Try uploading a smaller 1-to-2 page statement.")
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
