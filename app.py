from flask import Flask, render_template, jsonify, request
from src.helper import download_hugging_face_embeddings
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from src.prompt import *
import os
import requests

app = Flask(__name__)

load_dotenv()

PINECONE_API_KEY=os.environ.get('PINECONE_API_KEY')
GEMINI_API_KEY=os.environ.get('GEMINI_API_KEY')

os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

embeddings = download_hugging_face_embeddings()


index_name = "medicalbot"

# Embed each chunk and upsert the embeddings into your Pinecone index.
docsearch = PineconeVectorStore.from_existing_index(
    index_name=index_name,
    embedding=embeddings
)

retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k":3})


llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.4,
    max_output_tokens=500,
    google_api_key=GEMINI_API_KEY
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}"),
    ]
)

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)


# Helper to classify queries as medical or not using the existing Gemini LLM
def is_medical_query(query, llm):
    classifier_prompt = (
        "Analyze the following user query. Determine if it is a medical, health, symptom, disease, medicine, anatomy, treatment, wellness, or healthcare related query.\n"
        "Answer with ONLY a single word: 'YES' if it is medical-related, or 'NO' if it is not medical-related. Do not include any punctuation, explanation, or extra text.\n\n"
        f"Query: {query}"
    )
    try:
        response = llm.invoke([HumanMessage(content=classifier_prompt)])
        result = response.content.strip().upper()
        print(f"Medical classification result for '{query}': {result}")
        return "YES" in result
    except Exception as e:
        print(f"Error classifying query: {e}")
        # Default to True so that we don't block valid queries in case of an LLM error
        return True


# Helper to route queries to Sarvam AI's Chat Completion API
def ask_sarvam_ai(query):
    sarvam_api_key = os.environ.get("SARVAM_API_KEY")
    if not sarvam_api_key:
        print("SARVAM_API_KEY is not set in environment variables.")
        return "Error: Sarvam AI API key is not configured in the server's environment."
    
    url = "https://api.sarvam.ai/v1/chat/completions"
    headers = {
        "api-subscription-key": sarvam_api_key,
        "Authorization": f"Bearer {sarvam_api_key}",
        "Content-Type": "application/json"
    }
    
    # Use sarvam-30b as default, but allow custom models via SARVAM_MODEL
    model = os.environ.get("SARVAM_MODEL", "sarvam-30b")
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": query
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code != 200:
            print(f"Sarvam AI Error response: {response.status_code} - {response.text}")
        response.raise_for_status()
        result_json = response.json()
        answer = result_json["choices"][0]["message"]["content"]
        return answer
    except Exception as e:
        print(f"Error querying Sarvam AI: {e}")
        return "Sorry, I encountered an error while processing your request via Sarvam AI. Please try again later."


@app.route("/")
def index():
    return render_template('chat.html')


@app.route("/get", methods=["GET", "POST"])
def chat():
    msg = request.form["msg"]
    input = msg
    print("User message:", msg)
    
    # 1. Check if the query is medical-related
    if not is_medical_query(msg, llm):
        print("Query is not medical-related. Returning 'I don't know.'")
        return "I don't know."
        
    # 2. Query the RAG chain (from PDF context)
    response = rag_chain.invoke({"input": msg})
    answer = response["answer"].strip()
    print("RAG answer:", answer)
    
    # 3. If the answer was not found in the PDF context, fallback to Sarvam AI
    if "NOT_FOUND_IN_PDF" in answer:
        print("Answer not found in PDF. Routing to Sarvam AI...")
        answer = ask_sarvam_ai(msg)
        print("Sarvam AI answer:", answer)
        
    return str(answer)




if __name__ == '__main__':
    app.run(host="0.0.0.0", port= 8080, debug= True)
