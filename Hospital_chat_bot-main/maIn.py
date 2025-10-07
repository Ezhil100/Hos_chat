# =============================================================================
# IMPORTS
# =============================================================================
import os
import tempfile
import time
import firebase_admin
from firebase_admin import credentials, storage
from dotenv import load_dotenv 
import streamlit as st
from langchain_community.document_loaders import UnstructuredPDFLoader
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
working_dir = os.path.dirname(os.path.abspath(_file_))

# Initialize Firebase Admin SDK using Streamlit secrets
try:
    # Check if Firebase app is already initialized
    if not firebase_admin._apps:
        # Convert Streamlit secrets to dictionary for firebase_admin
        firebase_secrets = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_secrets)
        firebase_admin.initialize_app(cred, {
            'storageBucket': f"{firebase_secrets['project_id']}.firebasestorage.app"
        })
    
    bucket = storage.bucket()
    FIREBASE_INITIALIZED = True
except Exception as e:
    st.error(f"Firebase initialization failed: {e}")
    FIREBASE_INITIALIZED = False

# =============================================================================
# FIREBASE FUNCTIONS
# =============================================================================
def upload_file_to_firebase(file_path, file_name):
    """Uploads a file to Firebase Storage."""
    if not FIREBASE_INITIALIZED:
        return "Firebase not initialized. Skipped upload."
        
    try:
        if 'bucket' not in globals():
             return "Firebase bucket object is not available."
        
        blob = bucket.blob(file_name)
        blob.upload_from_filename(file_path)
        return f"File '{file_name}' uploaded successfully to Firebase Storage."
    except Exception as e:
        return f"Error uploading file: {e}"

def download_firebase_file(file_name):
    """Downloads a file from Firebase Storage to a temporary location."""
    if not FIREBASE_INITIALIZED:
        return None
        
    try:
        blob = bucket.blob(file_name)
        if not blob.exists():
            return None
            
        # Create a temporary file with the same extension
        file_extension = os.path.splitext(file_name)[1]
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_file_path = temp_file.name
        temp_file.close()
        
        # Download the file
        blob.download_to_filename(temp_file_path)
        return temp_file_path
    except Exception as e:
        st.error(f"Error downloading file {file_name}: {e}")
        return None

def list_firebase_files():
    """List all PDF files in Firebase Storage with their metadata."""
    if not FIREBASE_INITIALIZED:
        return []
        
    try:
        blobs = bucket.list_blobs()
        files_info = []
        
        for blob in blobs:
            if blob.name.lower().endswith('.pdf'):
                files_info.append({
                    'name': blob.name,
                    'size': blob.size or 0,
                    'created': blob.time_created,
                    'updated': blob.updated
                })
        
        return files_info
    except Exception as e:
        st.error(f"Error listing files: {e}")
        return []

# =============================================================================
# DOCUMENT PROCESSING FUNCTIONS
# =============================================================================
def load_document(file_path):
    """Load and process PDF document with multiple fallback methods."""
    documents = []
    file_name = os.path.basename(file_path)
    
    # Method 1: Try UnstructuredPDFLoader (primary)
    try:
        loader = UnstructuredPDFLoader(file_path)
        documents = loader.load()
        if documents:
            return documents
    except Exception as e:
        st.warning(f"UnstructuredPDFLoader failed for {file_name}: {e}")
    
    # Method 2: Try PyPDFLoader (fallback 1)
    try:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        if documents:
            return documents
    except Exception as e:
        st.warning(f"PyPDFLoader failed for {file_name}: {e}")
    
    # Method 3: Try PyMuPDF (fallback 2)
    try:
        import fitz  # PyMuPDF
        from langchain_core.documents import Document
        
        doc = fitz.open(file_path)
        documents = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                documents.append(Document(
                    page_content=text,
                    metadata={"source": file_name, "page": page_num + 1}
                ))
        
        doc.close()
        if documents:
            return documents
    except Exception as e:
        st.warning(f"PyMuPDF failed for {file_name}: {e}")
    
    # Method 4: Try PyPDF2 (fallback 3)
    try:
        import PyPDF2
        from langchain_core.documents import Document
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            documents = []
            
            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                if text.strip():
                    documents.append(Document(
                        page_content=text,
                        metadata={"source": file_name, "page": page_num + 1}
                    ))
        
        if documents:
            return documents
    except Exception as e:
        st.warning(f"PyPDF2 failed for {file_name}: {e}")
    
    # If all methods fail
    raise Exception(f"All PDF processing methods failed for {file_name}")

def setup_vectorstore(documents):
    """Create FAISS vectorstore with optimized settings."""
    if not documents:
        raise ValueError("No documents provided for vectorstore creation")
    
    # Optimized text splitter settings
    text_splitter = CharacterTextSplitter(
        separator='\n',
        chunk_size=800,  # Reduced from 1000 for faster processing
        chunk_overlap=100,  # Reduced from 200 for less redundancy
        length_function=len
    )
    
    # Progress tracking for large documents
    total_docs = len(documents)
    st.write(f"📄 Processing {total_docs} document pages...")
    
    # Split documents into chunks
    doc_chunks = text_splitter.split_documents(documents)
    
    # Limit chunks for very large documents (performance optimization)
    if len(doc_chunks) > 2000:
        st.warning(f"⚡ Large document detected ({len(doc_chunks)} chunks). Limiting to 2000 chunks for better performance.")
        doc_chunks = doc_chunks[:2000]
    
    # Initialize embeddings with caching
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    
    # Create vectorstore with batch processing
    chunk_count = len(doc_chunks)
    st.write(f"🔄 Creating vector store with {chunk_count} chunks...")
    
    # Process in batches for better performance and progress tracking
    batch_size = 100
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    if chunk_count <= batch_size:
        # Small dataset - process at once
        vectorstore = FAISS.from_documents(doc_chunks, embeddings)
        progress_bar.progress(1.0)
        status_text.text("✅ Vector store created successfully!")
    else:
        # Large dataset - process in batches
        vectorstore = None
        for i in range(0, chunk_count, batch_size):
            end_idx = min(i + batch_size, chunk_count)
            batch_chunks = doc_chunks[i:end_idx]
            
            # Update progress
            progress = end_idx / chunk_count
            progress_bar.progress(progress)
            status_text.text(f"Processing batch {i//batch_size + 1}/{(chunk_count-1)//batch_size + 1}...")
            
            if vectorstore is None:
                # Create initial vectorstore
                vectorstore = FAISS.from_documents(batch_chunks, embeddings)
            else:
                # Add to existing vectorstore
                batch_vectorstore = FAISS.from_documents(batch_chunks, embeddings)
                vectorstore.merge_from(batch_vectorstore)
        
        progress_bar.progress(1.0)
        status_text.text("✅ Vector store created successfully!")
    
    # Clear progress indicators after 2 seconds
    time.sleep(2)
    progress_bar.empty()
    status_text.empty()
    
    return vectorstore

def create_chain(vectorstore):
    """Create conversational retrieval chain."""
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0
    )

    retriever = vectorstore.as_retriever()
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
        verbose=True
    )
    return chain

# =============================================================================
# INCREMENTAL LOADING FUNCTIONS
# =============================================================================
def check_and_load_new_files():
    """Incrementally load only new files from Firebase with compact loading UI."""
    if not FIREBASE_INITIALIZED:
        return
    
    firebase_files = list_firebase_files()
    if not firebase_files:
        if 'loaded_firebase_files' not in st.session_state:
            st.info("📭 No PDF files found in Firebase Storage. Upload some files to get started!")
        return
    
    # Initialize loaded files tracking
    if 'loaded_firebase_files' not in st.session_state:
        st.session_state.loaded_firebase_files = set()
        st.session_state.all_documents = []
        st.session_state.document_count = 0
    
    # Find new files
    current_files = {f['name'] for f in firebase_files}
    new_files = [f for f in firebase_files if f['name'] not in st.session_state.loaded_firebase_files]
    
    if not new_files:
        # No new files, just ensure vectorstore exists
        if st.session_state.all_documents and 'vectorstore' not in st.session_state:
            with st.spinner("🔄 Rebuilding vector store..."):
                st.session_state.vectorstore = setup_vectorstore(st.session_state.all_documents)
                st.session_state.conversation_chain = create_chain(st.session_state.vectorstore)
        return
    
    # Show compact loading for new files only
    loader_container = st.empty()
    
    # Compact loader HTML
    loader_container.markdown(
        f'''<div style="
            position: fixed; 
            bottom: 20px; 
            left: 20px; 
            background: rgba(255,255,255,0.95); 
            padding: 10px 15px; 
            border-radius: 8px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
            border: 1px solid #e0e0e0; 
            z-index: 1000; 
            min-width: 250px; 
            max-width: 350px;">
            <p style="font-size: 12px; color: #666; margin: 0;">📥 Loading {len(new_files)} new file(s)...</p>
            <div style="height: 8px; margin: 5px 0; background: #f0f0f0; border-radius: 4px;">
                <div style="background: #4CAF50; height: 100%; width: 0%; border-radius: 4px; transition: width 0.3s;"></div>
            </div>
        </div>''',
        unsafe_allow_html=True
    )
    
    new_documents = []
    success_count = 0
    
    for i, file_info in enumerate(new_files):
        file_name = file_info['name']
        file_size_mb = file_info['size'] / (1024 * 1024)
        
        # Update compact progress
        progress = (i + 1) / len(new_files)
        progress_html = f'''
        <div style="
            position: fixed; 
            bottom: 20px; 
            left: 20px; 
            background: rgba(255,255,255,0.95); 
            padding: 10px 15px; 
            border-radius: 8px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
            border: 1px solid #e0e0e0; 
            z-index: 1000; 
            min-width: 250px; 
            max-width: 350px;">
            <p style="font-size: 12px; color: #666; margin: 0;">📄 {file_name} ({file_size_mb:.1f}MB) - {i+1}/{len(new_files)}</p>
            <div style="height: 8px; margin: 5px 0; background: #f0f0f0; border-radius: 4px;">
                <div style="background: #4CAF50; height: 100%; width: {progress*100}%; border-radius: 4px; transition: width 0.3s;"></div>
            </div>
        </div>
        '''
        loader_container.markdown(progress_html, unsafe_allow_html=True)
        
        temp_file_path = download_firebase_file(file_name)
        if temp_file_path:
            try:
                documents = load_document(temp_file_path)
                
                # Limit pages for very large documents
                if len(documents) > 500:
                    documents = documents[:500]
                
                new_documents.extend(documents)
                success_count += 1
                st.session_state.loaded_firebase_files.add(file_name)
                os.remove(temp_file_path)
                
            except Exception as e:
                st.error(f"Failed to process {file_name}: {e}")
    
    # Combine with existing documents
    if new_documents:
        st.session_state.all_documents.extend(new_documents)
        st.session_state.document_count += success_count
        
        # Update vectorstore with all documents
        loader_container.markdown(
            '''<div style="
                position: fixed; 
                bottom: 20px; 
                left: 20px; 
                background: rgba(255,255,255,0.95); 
                padding: 10px 15px; 
                border-radius: 8px; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
                border: 1px solid #e0e0e0; 
                z-index: 1000; 
                min-width: 250px; 
                max-width: 350px;">
                <p style="font-size: 12px; color: #666; margin: 0;">🔄 Updating vector store...</p>
            </div>''',
            unsafe_allow_html=True
        )
        
        st.session_state.vectorstore = setup_vectorstore(st.session_state.all_documents)
        st.session_state.conversation_chain = create_chain(st.session_state.vectorstore)
        
        # Success message
        loader_container.markdown(
            f'''<div style="
                position: fixed; 
                bottom: 20px; 
                left: 20px; 
                background: #d4edda; 
                border: 1px solid #c3e6cb; 
                padding: 10px 15px; 
                border-radius: 8px; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
                z-index: 1000; 
                min-width: 250px; 
                max-width: 350px;">
                <p style="font-size: 12px; color: #155724; margin: 0;">✅ Added {success_count} new files! Total: {st.session_state.document_count}</p>
            </div>''',
            unsafe_allow_html=True
        )
        
        # Clear loader after 3 seconds
        time.sleep(3)
        loader_container.empty()
    else:
        loader_container.empty()

def auto_load_all_firebase_files():
    """Initial load and setup for Firebase files."""
    if 'auto_loaded' not in st.session_state:
        st.session_state.auto_loaded = True
        check_and_load_new_files()

# =============================================================================
# CHAT FUNCTIONS
# =============================================================================
def show_chat_interface_always():
    """Show chat interface that works with or without documents."""
    
    # Chat input
    user_question = st.chat_input("Type your message here...")
    
    if user_question:
        # Check if we have a conversation chain
        if 'conversation_chain' in st.session_state and st.session_state.conversation_chain:
            # Use document-based conversation
            with st.spinner("🤔 Thinking..."):
                response = st.session_state.conversation_chain.invoke({'question': user_question})
                
            # Add to chat history
            st.session_state.chat_history.append({"role": "user", "content": user_question})
            st.session_state.chat_history.append({"role": "assistant", "content": response['answer']})
        else:
            # Fallback to basic LLM without documents
            try:
                llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
                with st.spinner("🤔 Thinking..."):
                    response = llm.invoke(f"You are a helpful hospital assistant. Answer this question: {user_question}")
                
                st.session_state.chat_history.append({"role": "user", "content": user_question})
                st.session_state.chat_history.append({"role": "assistant", "content": response.content})
            except Exception as e:
                st.error(f"Error generating response: {e}")
    
    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

# =============================================================================
# MAIN APPLICATION
# =============================================================================
def main():
    """Main application function with incremental loading and compact UI."""
    st.set_page_config(
        page_title="KG_CHATBOT",
        page_icon="🤖",
        layout="centered"
    )
    
    # Custom CSS for clean GPT-inspired dark mode
    st.markdown("""
    <style>
    /* Main container styling */
    .stApp {
        background-color: #1e1e1e;
        color: #ffffff;
    }
    
    /* Title styling */
    .main-title {
        color: #4A9EFF;
        font-size: 2.5rem;
        font-weight: 600;
        text-align: center;
        margin: 2rem 0 3rem 0;
        letter-spacing: 1px;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #2d2d2d;
    }
    
    /* Chat messages styling */
    .stChatMessage {
        background-color: transparent;
        border: none;
    }
    
    /* Input box styling */
    .stChatInputContainer {
        background-color: #2d2d2d;
        border-radius: 8px;
    }
    
    /* Button styling */
    .stButton > button {
        background-color: #4A9EFF;
        color: white;
        border: none;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #357ABD;
        transform: translateY(-1px);
    }
    
    /* Success/info message styling */
    .stSuccess, .stInfo {
        background-color: rgba(74, 158, 255, 0.1);
        border-left: 3px solid #4A9EFF;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #2d2d2d;
        color: #ffffff;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Clean title
    st.markdown("""
    <div class="main-title">
        KG_CHATBOT
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    # Auto-load Firebase files on startup
    auto_load_all_firebase_files()
    
    # Check for new files periodically (every 30 seconds)
    if 'last_check_time' not in st.session_state:
        st.session_state.last_check_time = time.time()
    
    current_time = time.time()
    if current_time - st.session_state.last_check_time > 30:  # 30 seconds
        st.session_state.last_check_time = current_time
        check_and_load_new_files()
    
    # Sidebar for document management and status
    with st.sidebar:
        st.header("� Documents")
        
        # Manual refresh button
        if st.button("🔄 Check for New Files", help="Manually check Firebase for new uploads"):
            st.session_state.last_check_time = 0  # Force check
            check_and_load_new_files()
            st.rerun()
        
        # Show document status
        doc_count = st.session_state.get('document_count', 0)
        if doc_count > 0:
            st.success(f"✅ {doc_count} documents loaded")
        else:
            st.info("📭 No documents loaded")
            
        # Show Firebase status
        if FIREBASE_INITIALIZED:
            firebase_files = list_firebase_files()
            if firebase_files:
                loaded_count = len(st.session_state.get('loaded_firebase_files', set()))
                st.write(f"📊 *Total:* {len(firebase_files)} | *Loaded:* {loaded_count}")
                
                if loaded_count < len(firebase_files):
                    st.write(f"⏳ *New files:* {len(firebase_files) - loaded_count}")
                
                with st.expander("📋 File Details"):
                    for file_info in firebase_files:
                        size_mb = file_info['size'] / (1024 * 1024)
                        status = "✅" if file_info['name'] in st.session_state.get('loaded_firebase_files', set()) else "🆕"
                        st.write(f"{status} {file_info['name']} ({size_mb:.1f}MB)")
            else:
                st.write("📭 No files in Firebase Storage")
        else:
            st.warning("⚠ Firebase not initialized")
        
        # Management options
        st.subheader("🛠 Management")
        
        if st.button("🔄 Force Reload All"):
            # Clear all tracking to force full reload
            for key in ['auto_loaded', 'loaded_firebase_files', 'all_documents', 'vectorstore', 'conversation_chain', 'document_count']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Always show chat interface (even if no documents loaded initially)
    show_chat_interface_always()

if __name__ == "__main__":
    main()