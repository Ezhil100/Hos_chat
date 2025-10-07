# Hospital AI Assistant - RAG-Based Chatbot

A modern, full-stack hospital AI assistant built with React frontend and FastAPI backend, featuring role-based authentication, RAG (Retrieval Augmented Generation) system, and document management capabilities.

## 🚀 Features

- **Role-Based Access Control**: Separate interfaces for Patients, Visitors, Staff, and Admins
- **RAG System**: Context-aware responses using document retrieval and LLM integration
- **Document Management**: Upload and manage PDF documents for the knowledge base
- **Real-time Chat**: Instant responses with typing indicators and message history
- **Admin Dashboard**: System status monitoring, document uploads, and vector store management
- **Nothing OS-Inspired UI**: Clean, geometric icons with minimalist design
- **Responsive Design**: Works seamlessly on desktop and mobile devices
- **JWT Authentication**: Secure token-based authentication system

## 📋 Prerequisites

- **Python**: 3.9 or higher
- **Node.js**: 16.x or higher
- **npm** or **yarn**
- **Ollama**: For local LLM inference
- **Firebase**: Account for Firestore database (optional)

## 🛠️ Tech Stack

### Frontend
- React 18
- Inline CSS (Nothing OS style)
- Fetch API for HTTP requests

### Backend
- FastAPI
- LangChain
- Ollama (LLM)
- FAISS (Vector Store)
- Firebase Firestore
- PyPDF2
- JWT Authentication
- python-multipart

## 📦 Installation

### Backend Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd hospital-ai-assistant
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install fastapi uvicorn langchain langchain-community ollama faiss-cpu pypdf2 firebase-admin python-jose[cryptography] passlib[bcrypt] python-multipart
```

4. **Set up Firebase**
   - Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
   - Download service account key JSON file
   - Place it as `serviceAccountKey.json` in the backend directory

5. **Configure Ollama**
```bash
# Install Ollama from https://ollama.ai
# Pull the model
ollama pull llama2
```

6. **Create backend structure**
```
backend/
├── main.py
├── serviceAccountKey.json
└── documents/  # Create this folder for PDF uploads
```

7. **Run the backend**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

1. **Create React app**
```bash
npx create-react-app hospital-chatbot
cd hospital-chatbot
```

2. **Replace App.js with the provided code**
   - Copy the complete React code to `src/App.js`

3. **Update API endpoint (if needed)**
```javascript
const API_BASE_URL = 'http://localhost:8000';
```

4. **Start the development server**
```bash
npm start
```

The app will open at `http://localhost:3000`

## 🔑 Default Credentials

### Admin
- **Username**: `admin`
- **Password**: `admin123`

### Staff
- **Username**: `staff1`
- **Password**: `staff123`

### Patient
- **Username**: `patient1`
- **Password**: `patient123`

### Visitor
- **Username**: `visitor1`
- **Password**: `visitor123`

## 📁 Project Structure

```
hospital-ai-assistant/
├── backend/
│   ├── main.py                    # FastAPI application
│   ├── serviceAccountKey.json     # Firebase credentials
│   └── documents/                 # PDF storage directory
│
└── frontend/
    ├── public/
    ├── src/
    │   ├── App.js                 # Main React component
    │   └── index.js               # Entry point
    ├── package.json
    └── README.md
```

## 🎯 Usage

### For Patients
- Find doctors and specialists
- Book appointments
- Get treatment information
- Access emergency contacts

### For Visitors
- Check visiting hours
- Get hospital location and parking info
- Learn about amenities

### For Staff
- Patient inquiries
- Department information
- Emergency protocols
- Hospital policies

### For Admins
- **System Status**: Monitor Firebase, vector store, and document loading
- **Upload Documents**: Add PDF files to the knowledge base
- **Reload System**: Refresh the vector store with new documents
- **Dashboard**: Comprehensive system overview

## 🔧 API Endpoints

### Authentication
- `POST /auth/login` - User login
- `GET /auth/verify` - Verify JWT token

### Chat
- `POST /chat` - Send message and get AI response

### Admin
- `POST /admin/upload-document` - Upload PDF document
- `GET /admin/documents` - List all documents
- `POST /admin/reload-documents` - Reload vector store

### System
- `GET /system/status` - Get system status

## 🎨 Customization

### Change Color Scheme
Edit the gradient colors in `App.js`:
```javascript
background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
```

### Modify LLM Model
In `main.py`:
```python
llm = Ollama(model="llama2")  # Change to your preferred model
```

### Add More User Roles
Update the `quickActions` object and backend role validation.

## 🐛 Troubleshooting

### Backend won't start
- Ensure Ollama is running: `ollama serve`
- Check Firebase credentials are valid
- Verify all Python dependencies are installed

### Frontend connection error
- Confirm backend is running on port 8000
- Check CORS settings in `main.py`
- Verify API_BASE_URL is correct

### Document upload fails
- Ensure `documents/` folder exists
- Check file permissions
- Verify PDF file is valid

### Chat responses are slow
- Ollama model may need better hardware
- Consider using smaller models (e.g., `llama2:7b`)
- Check system resources

## 📝 Environment Variables (Optional)

Create `.env` file in backend:
```
FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json
OLLAMA_HOST=http://localhost:11434
JWT_SECRET_KEY=your-secret-key-here
```

## 🚀 Deployment

### Backend (Railway/Render)
1. Add `requirements.txt`
2. Set environment variables
3. Configure external Ollama endpoint

### Frontend (Vercel/Netlify)
1. Update `API_BASE_URL` to production URL
2. Build: `npm run build`
3. Deploy `build/` directory

## 📄 License

MIT License - feel free to use this project for personal or commercial purposes.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📧 Support

For issues or questions, please open a GitHub issue or contact the maintainers.

## 🙏 Acknowledgments

- **Nothing OS** for design inspiration
- **LangChain** for RAG framework
- **Ollama** for local LLM inference
- **FastAPI** for backend framework
- **React** for frontend framework

***

**Built with ❤️ for healthcare accessibility**