# main.py - No Authentication Version
import re
import os
import tempfile
import time
from datetime import datetime
from typing import List
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, storage
from dotenv import load_dotenv

# LangChain imports
from langchain_community.document_loaders import UnstructuredPDFLoader, PyPDFLoader
from langchain_text_splitters.character import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain

# =============================================================================
# CONFIGURATION & INITIALIZATION
# =============================================================================
load_dotenv()

app = FastAPI(
    title="KG Hospital AI Chatbot API",
    version="1.0.0",
    description="AI-powered chatbot system for KG Hospital"
)

PORT = int(os.getenv("PORT", 8000))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hospital-chat-bot.vercel.app",
        "https://hospital-chat-bot-frontend-9ds2.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin SDK
try:
    if not firebase_admin._apps:
        firebase_config = {
            "type": "service_account",
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }

        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred, {
            'storageBucket': f"{firebase_config['project_id']}.firebasestorage.app"
        })

    bucket = storage.bucket()
    FIREBASE_INITIALIZED = True
    print("Firebase initialized successfully")
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    FIREBASE_INITIALIZED = False

vectorstore = None
conversation_chain = None
loaded_documents = []

# =============================================================================
# PYDANTIC MODELS
# =============================================================================
class ChatMessage(BaseModel):
    message: str
    user_role: str = "patient"

class ChatResponse(BaseModel):
    response: str
    timestamp: str

# =============================================================================
# DOCUMENT PROCESSING FUNCTIONS
# =============================================================================
def load_document(file_path: str):
    documents = []
    file_name = os.path.basename(file_path)

    try:
        loader = UnstructuredPDFLoader(file_path)
        documents = loader.load()
        if documents:
            print(f"Loaded {file_name} using UnstructuredPDFLoader")
            return documents
    except Exception as e:
        print(f"UnstructuredPDFLoader failed for {file_name}: {e}")

    try:
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        if documents:
            print(f"Loaded {file_name} using PyPDFLoader")
            return documents
    except Exception as e:
        print(f"PyPDFLoader failed for {file_name}: {e}")

    raise Exception(f"All PDF processing methods failed for {file_name}")

def setup_vectorstore(documents):
    if not documents:
        raise ValueError("No documents provided for vectorstore creation")

    print(f"Processing {len(documents)} document pages...")

    text_splitter = CharacterTextSplitter(
        separator='\n',
        chunk_size=800,
        chunk_overlap=100,
        length_function=len
    )

    doc_chunks = text_splitter.split_documents(documents)
    print(f"Created {len(doc_chunks)} text chunks")

    if len(doc_chunks) > 2000:
        print("Large document detected. Limiting to 2000 chunks for performance.")
        doc_chunks = doc_chunks[:2000]

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

    print("Creating vector store...")
    vectorstore = FAISS.from_documents(doc_chunks, embeddings)
    print("Vector store created successfully!")

    return vectorstore

def create_chain(vectorstore):
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5}
    )

    memory = ConversationBufferMemory(
        llm=llm,
        output_key='answer',
        memory_key='chat_history',
        return_messages=True
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        verbose=False,
        return_source_documents=False
    )

    return chain

# =============================================================================
# FIREBASE FUNCTIONS
# =============================================================================
def upload_file_to_firebase(file_path: str, file_name: str):
    if not FIREBASE_INITIALIZED:
        return False, "Firebase not initialized"

    try:
        blob = bucket.blob(f"documents/{file_name}")
        blob.upload_from_filename(file_path)
        print(f"Uploaded {file_name} to Firebase Storage")
        return True, f"File '{file_name}' uploaded successfully"
    except Exception as e:
        print(f"Upload failed for {file_name}: {e}")
        return False, f"Upload failed: {str(e)}"

def list_firebase_files():
    if not FIREBASE_INITIALIZED:
        return []

    try:
        blobs = bucket.list_blobs(prefix="documents/")
        files_info = []

        for blob in blobs:
            if blob.name.lower().endswith('.pdf'):
                files_info.append({
                    'name': blob.name.replace('documents/', ''),
                    'size': blob.size or 0,
                    'created': blob.time_created.isoformat() if blob.time_created else '',
                    'status': 'loaded'
                })

        return files_info
    except Exception as e:
        print(f"Error listing files: {e}")
        return []

def download_firebase_file(file_name: str):
    if not FIREBASE_INITIALIZED:
        return None

    try:
        blob = bucket.blob(f"documents/{file_name}")
        if not blob.exists():
            return None

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        temp_file_path = temp_file.name
        temp_file.close()

        blob.download_to_filename(temp_file_path)
        return temp_file_path
    except Exception as e:
        print(f"Download failed for {file_name}: {e}")
        return None

def reload_all_documents():
    global vectorstore, conversation_chain, loaded_documents

    print("Reloading all documents from Firebase...")
    firebase_files = list_firebase_files()
    if not firebase_files:
        return False, "No documents found in Firebase"

    all_documents = []
    successful_loads = 0

    for file_info in firebase_files:
        file_name = file_info['name']
        print(f"Processing {file_name}...")

        temp_file_path = download_firebase_file(file_name)
        if temp_file_path:
            try:
                documents = load_document(temp_file_path)
                all_documents.extend(documents)
                successful_loads += 1
                os.remove(temp_file_path)
            except Exception as e:
                print(f"Failed to process {file_name}: {e}")
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

    if all_documents:
        print(f"Total documents loaded: {len(all_documents)}")
        vectorstore = setup_vectorstore(all_documents)
        conversation_chain = create_chain(vectorstore)
        loaded_documents = all_documents
        return True, f"Successfully loaded {successful_loads} out of {len(firebase_files)} documents"

    return False, "No documents could be processed"

# =============================================================================
# CHAT ENDPOINT WITH FORMATTED OUTPUT
# =============================================================================
@app.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """Chat endpoint with user-friendly, readable responses."""
    global conversation_chain

    try:
        print(f"Chat request ({message.user_role}): {message.message}")

        if conversation_chain:
            response = conversation_chain.invoke({'question': message.message})
            answer = response.get('answer', '')
        else:
            llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

            system_prompts = {
                "patient": """You are a helpful KG Hospital AI assistant helping patients. 
                
                Provide clear, organized information about:
                - Doctor appointments and specializations
                - Hospital services and departments  
                - Treatment information and medical procedures
                - Emergency contacts and protocols
                
                Format your responses using natural sentences and organize lists clearly.
                Use department names followed by descriptions.
                If information is unavailable, guide the user to contact the hospital front desk or helpline for detailed assistance.""",

                "visitor": """You are a helpful KG Hospital AI assistant helping visitors.
                
                Provide clear information about:
                - Visiting hours and policies
                - Hospital location and directions
                - Parking information and facilities
                - Hospital amenities and services
                
                Format your answers using natural sentences and organize information clearly.
                If information is unavailable, kindly suggest the visitor reach the hospital's help desk for more information.""",

                "staff": """You are a helpful KG Hospital AI assistant helping hospital staff.
                
                Provide organized information about:
                - Patient inquiry responses
                - Department information and contacts
                - Emergency protocols and procedures
                - Hospital policies and guidelines
                
                Format your answers using clear sentences and organize information logically.
                If details are unavailable, politely mention that the staff can consult the hospital administration for accurate information.""",

                "admin": """You are a helpful KG Hospital AI assistant helping administrators.
                
                Provide comprehensive information about:
                - Hospital operations and management
                - System status and analytics
                - Administrative procedures
                - Staff coordination and policies
                
                Format your output using clear paragraphs and organize information systematically.
                If certain data is not accessible, inform that the admin team can review internal records or contact support for help."""
            }

            system_prompt = system_prompts.get(message.user_role, system_prompts["patient"])
            full_prompt = f"{system_prompt}\n\nUser Question: {message.message}\n\nResponse:"
            response = llm.invoke(full_prompt)
            answer = response.content

        if not answer.strip() or "I don't know" in answer or "I'm not sure" in answer:
            answer = ("I'm happy to help with your query. "
                      "While I don’t have specific information on that at the moment, "
                      "you can contact KG Hospital’s support or visit the front desk anytime for assistance.")

        formatted_answer = format_response_text(answer)

        return ChatResponse(
            response=formatted_answer,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        print(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

# =============================================================================
# RESPONSE FORMATTER
# =============================================================================
def format_response_text(text: str) -> str:
    """Format chatbot output into clean, ChatGPT-like layout for React frontend."""
    import re
    if not text:
        return "I'm happy to assist. You can also contact KG Hospital for detailed guidance."

    # Clean up the text first
    original_text = text.strip()
    
    # Check if this looks like a table request or table data
    if 'table format' in original_text.lower() or ('|' in original_text and '---' in original_text):
        return original_text  # Return as-is for table formatting
    
    # Fix broken numbered lists where numbers appear on separate lines
    # First, normalize the text and fix common AI formatting issues
    text = original_text
    
    # Fix patterns like "1.\nName" or "1. Name 2.\nNext name"
    text = re.sub(r'(\d+\.)\s*\n\s*([A-Za-z])', r'\1 \2', text)
    
    # Fix patterns where multiple items run together
    text = re.sub(r'([A-Za-z\)]\s+)(\d+\.)(?=\s*[A-Za-z])', r'\1\n\2', text)
    
    # Fix standalone numbers that got separated
    text = re.sub(r'\n\s*(\d+)\s*\n\s*(\d+\.)', r'\n\1\2', text)
    
    lines = []
    
    # Split into lines and process sequentially to maintain order
    raw_lines = text.split('\n')
    
    current_number = 0
    pending_number = None
    
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if this line is just a standalone number
        if re.match(r'^\d+$', line):
            pending_number = int(line)
            continue
        
        # Check if this line starts with a number
        number_match = re.match(r'^(\d+\.)\s*(.+)', line)
        if number_match:
            number = number_match.group(1)
            content = number_match.group(2).strip()
            
            # Clean up content
            content = re.sub(r'\s+', ' ', content)
            content = content.rstrip('.')
            
            lines.append(f"{number} {content}")
            current_number = int(number.rstrip('.'))
            pending_number = None
            continue
        
        # Check if we have a pending number and this line has content
        if pending_number is not None and line and not line.startswith(str(pending_number)):
            # This content belongs to the pending number
            content = line.strip().rstrip('.')
            content = re.sub(r'\s+', ' ', content)
            lines.append(f"{pending_number}. {content}")
            current_number = pending_number
            pending_number = None
            continue
        
        # Handle non-numbered content (headers, descriptions, etc.)
        if not re.match(r'^\d+', line):
            # This is regular text
            if 'department' in line.lower():
                dept_match = re.search(r'([A-Za-z\s]+department)', line, re.IGNORECASE)
                if dept_match:
                    dept_name = dept_match.group(1).title()
                    lines.append("")
                    lines.append(f"**{dept_name}**")
                    
                    remaining = line[dept_match.end():].strip()
                    if remaining.startswith(':') or remaining.startswith('is:'):
                        remaining = re.sub(r'^:?\s*is:?\s*', '', remaining)
                    if remaining:
                        lines.append(remaining)
                    lines.append("")
                    continue
            
            # Regular descriptive text
            if any(phrase in line.lower() for phrase in ['mentioned:', 'list of', 'includes', 'following', 'columns:']):
                lines.append(line)
                continue
                
            lines.append(line)
    
    # Clean up the results
    formatted_text = '\n'.join(lines)
    
    # Clean up excessive whitespace while preserving intentional spacing
    formatted_text = re.sub(r'\n{3,}', '\n\n', formatted_text)
    formatted_text = re.sub(r'^\n+', '', formatted_text)  # Remove leading newlines
    formatted_text = re.sub(r'\n+$', '', formatted_text)  # Remove trailing newlines
    
    return formatted_text

# =============================================================================
# OTHER ENDPOINTS
# =============================================================================
@app.get("/")
async def root():
    return {
        "message": "KG Hospital AI Chatbot API",
        "status": "running",
        "version": "1.0.0",
        "firebase_initialized": FIREBASE_INITIALIZED,
        "documents_loaded": len(loaded_documents) > 0
    }

@app.post("/upload-document")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    temp_file_path = temp_file.name

    try:
        content = await file.read()
        temp_file.write(content)
        temp_file.close()

        success, message = upload_file_to_firebase(temp_file_path, file.filename)

        if success:
            reload_success, reload_message = reload_all_documents()
            os.remove(temp_file_path)

            if reload_success:
                return {"message": f"Document uploaded and processed successfully: {message}",
                        "reload_status": reload_message, "filename": file.filename}
            else:
                return {"message": f"Document uploaded but processing failed: {reload_message}",
                        "filename": file.filename}
        else:
            os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail=message)

    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/documents")
async def list_documents():
    documents = list_firebase_files()
    return {"documents": documents, "count": len(documents), "firebase_status": FIREBASE_INITIALIZED}

@app.post("/reload-documents")
async def reload_documents_endpoint():
    success, message = reload_all_documents()
    if success:
        return {"message": message, "status": "success", "documents_loaded": len(loaded_documents)}
    else:
        raise HTTPException(status_code=500, detail=message)

@app.get("/system/status")
async def system_status():
    return {
        "firebase_initialized": FIREBASE_INITIALIZED,
        "documents_loaded": len(loaded_documents),
        "vectorstore_ready": vectorstore is not None,
        "conversation_chain_ready": conversation_chain is not None,
        "groq_api_configured": bool(os.getenv("GROQ_API_KEY")),
        "timestamp": datetime.now().isoformat()
    }

@app.on_event("startup")
async def startup_event():
    print("Starting KG Hospital Chatbot API...")
    print(f"Firebase Status: {'Connected' if FIREBASE_INITIALIZED else 'Not Connected'}")

    if FIREBASE_INITIALIZED:
        print("Loading initial documents...")
        success, message = reload_all_documents()
        if success:
            print(message)
        else:
            print(message)

    print("KG Hospital Chatbot API is ready!")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")