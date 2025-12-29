"""
Vector Store - ChromaDB integration for RAG
"""
import chromadb
from chromadb.config import Settings
import config.settings as settings
from sentence_transformers import SentenceTransformer

class VectorStore:
    """Manages vector storage and retrieval using ChromaDB"""
    
    def __init__(self):
        """Initialize ChromaDB and embedding model"""
        print("Initializing ChromaDB...")
        
        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(settings.CHROMADB_DIR)
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="meeting_transcripts",
            metadata={"description": "Meeting transcripts for semantic search"}
        )
        
        # Load embedding model
        print(f"Loading embedding model: {settings.EMBEDDING_MODEL}...")
        self.embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        
        print("✓ Vector Store initialized")
    
    def add_meeting(self, meeting_id, transcript, metadata=None):
        """
        Add a meeting transcript to the vector store
        
        Args:
            meeting_id: Unique meeting identifier
            transcript: Meeting transcript text
            metadata: Additional metadata (title, date, participants)
        """
        try:
            # Chunk the transcript
            chunks = self._chunk_text(transcript)
            
            # Create IDs for chunks
            chunk_ids = [f"{meeting_id}_chunk_{i}" for i in range(len(chunks))]
            
            # Prepare metadata
            chunk_metadata = []
            for i in range(len(chunks)):
                meta = {
                    'meeting_id': meeting_id,
                    'chunk_index': i,
                    **(metadata or {})
                }
                chunk_metadata.append(meta)
            
            # Add to collection
            self.collection.add(
                ids=chunk_ids,
                documents=chunks,
                metadatas=chunk_metadata
            )
            
            print(f"✓ Added {len(chunks)} chunks for meeting {meeting_id}")
            
        except Exception as e:
            print(f"❌ Error adding meeting to vector store: {e}")
            raise
    
    def get_relevant_context(self, query, max_chunks=3):
        """
        Retrieve relevant context for a query
        
        Args:
            query: Search query
            max_chunks: Maximum number of chunks to return
        
        Returns:
            str: Concatenated relevant text chunks
        """
        try:
            # Query the collection
            results = self.collection.query(
                query_texts=[query],
                n_results=max_chunks
            )
            
            if not results['documents'] or not results['documents'][0]:
                return ""
            
            # Concatenate results
            context = "\n\n".join(results['documents'][0])
            return context
            
        except Exception as e:
            print(f"❌ Error retrieving context: {e}")
            return ""
    
    def search_meetings(self, query, n_results=5):
        """
        Search for relevant meetings
        
        Args:
            query: Search query
            n_results: Number of results to return
        
        Returns:
            dict: Search results with documents and metadata
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            return results
        except Exception as e:
            print(f"❌ Error searching meetings: {e}")
            return {'documents': [], 'metadatas': []}
    
    def delete_meeting(self, meeting_id):
        """
        Delete all chunks for a meeting
        
        Args:
            meeting_id: Meeting identifier
        """
        try:
            # Get all chunk IDs for this meeting
            results = self.collection.get(
                where={"meeting_id": meeting_id}
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                print(f"✓ Deleted {len(results['ids'])} chunks for meeting {meeting_id}")
        except Exception as e:
            print(f"❌ Error deleting meeting: {e}")
    
    def _chunk_text(self, text):
        """
        Split text into chunks for embedding
        
        Args:
            text: Text to chunk
        
        Returns:
            list: Text chunks
        """
        # Simple chunking by sentences
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < settings.CHUNK_SIZE:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text]
    
    def get_stats(self):
        """Get vector store statistics"""
        count = self.collection.count()
        return {
            'total_chunks': count,
            'collection_name': self.collection.name
        }
