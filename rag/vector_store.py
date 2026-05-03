"""
Vector Store - ChromaDB integration for RAG
"""
import chromadb
from chromadb.config import Settings
import config.settings as settings
from sentence_transformers import SentenceTransformer

from chromadb.utils import embedding_functions

class VectorStore:
    """Manages vector storage and retrieval using ChromaDB"""
    
    def __init__(self):
        """Initialize ChromaDB and embedding model"""
        print("Initializing ChromaDB...")
        
        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(settings.CHROMADB_DIR)
        )
        
        # Create embedding function for ChromaDB
        print(f"Loading embedding model: {settings.EMBEDDING_MODEL}...")
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL
        )
        
        # Get or create collection with the embedding function
        self.collection = self.client.get_or_create_collection(
            name="meeting_transcripts",
            embedding_function=self.embedding_function,
            metadata={"description": "Meeting transcripts for semantic search", "hnsw:space": "cosine"}
        )
        
        print("[SUCCESS] Vector Store initialized")
    

    def add_meeting(self, meeting_id, transcript, summary=None, action_items=None, metadata=None):
        try:
            base_meta = {
                "meeting_id": meeting_id,
                "title": metadata.get("title") if metadata else None,
                "date": metadata.get("date") if metadata else None,
                "participants": metadata.get("participants") if metadata else None,
            }

            all_chunks = []
            all_metadata = []
            all_ids = []

            # 1. TRANSCRIPT CHUNKS
            transcript_chunks = self._chunk_text(transcript)

            for i, chunk in enumerate(transcript_chunks):
                all_metadata.append({
                    **base_meta,
                    "source": "transcript",
                    "chunk_index": i
                })
                metatext= f"""
                        Title: {metadata.get('title', '')}
                        Date: {metadata.get('date', '')}
                        Participants: {metadata.get('participants', '')}
                        Source: Transcript
                        """
                chunk_with_metatext= metatext + "\n" + chunk
                all_ids.append(f"{meeting_id}_t_{i}")
                all_chunks.append(chunk_with_metatext)

            # 2. SUMMARY
            if summary:
                summary_chunks = self._chunk_summary(summary)

                for i, chunk in enumerate(summary_chunks):
                    summary_meta={
                        **base_meta,
                        "source": "summary",
                        "chunk_index": i
                    }
                    summary_metatext= f"""
                        Title: {metadata.get('title', '')}
                        Date: {metadata.get('date', '')}
                        Participants: {metadata.get('participants', '')}
                        Source: Summary
                        """
                    chunk_with_meta= summary_metatext + "\n" + chunk
                    all_metadata.append(summary_meta)
                    all_ids.append(f"{meeting_id}_summary_{i}")
                    all_chunks.append(chunk_with_meta)

            # 3. ACTION ITEMS
            if action_items:
                for i, item in enumerate(action_items):
                # Convert structured item → text
                    text = f"""
                    Task: {item.get('task')}
                    Owner: {item.get('owner', 'Unassigned')}
                    Deadline: {item.get('deadline', 'Not specified')}
                    Priority: {item.get('priority', 'medium')}
                    """
                    action_metatext= f"""
                        Title: {metadata.get('title', '')}
                        Date: {metadata.get('date', '')}
                        Participants: {metadata.get('participants', '')}
                        Source: Action Item
                        """
                    chunk= text + "\n" + action_metatext
                    all_metadata.append({
                        **base_meta,
                        "source": "action_item",
                        "chunk_index": i
                    })
                    all_chunks.append(chunk)
                    all_ids.append(f"{meeting_id}_action_{i}")

            # STORE IN CHROMA
            self.collection.add(
                ids=all_ids,
                documents=all_chunks,
                metadatas=all_metadata
            )

            print(f"[SUCCESS] Stored all data for {meeting_id}")

        except Exception as e:
            print(f"[ERROR] {e}")
            raise
    
    '''    def add_meeting(self, meeting_id, transcript, metadata=None):
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
            
            meta_text = f"""
            Title: {metadata.get('title', '')}
            Date: {metadata.get('date', '')}
            Participants: {metadata.get('participants', '')}
            """

            chunks_with_metadata = [meta_text + "\n" + chunk for chunk in chunks]
            # Add to collection
            self.collection.add(
                ids=chunk_ids,
                documents=chunks_with_metadata,
                metadatas=chunk_metadata
            )
            
            print(f"[SUCCESS] Added {len(chunks)} chunks for meeting {meeting_id}")
            
        except Exception as e:
            print(f"[ERROR] Error adding meeting to vector store: {e}")
            raise
   '''
    def get_relevant_context(self, query, max_chunks=5):
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
            print(f"[ERROR] Error retrieving context: {e}")
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
            print(f"[ERROR] Error searching meetings: {e}")
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
                print(f"[SUCCESS] Deleted {len(results['ids'])} chunks for meeting {meeting_id}")
        except Exception as e:
            print(f"[ERROR] Error deleting meeting: {e}")
    
    '''def _chunk_text(self, text):
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
        
        return chunks if chunks else [text]'''
    
    def _chunk_text(self, text):
        """
            Improved chunking with overlap and word-based splitting
            
            Args:
                text: Text to chunk
            
            Returns:
                list: Text chunks
            """
        if not text:
                return []

        words = text.split()

        chunk_size = settings.CHUNK_SIZE  # interpret as number of words
        overlap = int(chunk_size * 0.2)   # 20% overlap

        chunks = []
        start = 0

        while start < len(words):
            end = start + chunk_size
            chunk_words = words[start:end]

            chunk = " ".join(chunk_words).strip()
            if chunk:
                chunks.append(chunk)

                # move forward with overlap
            start += (chunk_size - overlap)

        return chunks if chunks else [text]
    
    def _chunk_summary(self, summary):
        """
        Chunk summary into smaller coherent pieces
        """
        if not summary:
            return []

        words = summary.split()

        chunk_size = 80   # smaller than transcript
        overlap = 20

        chunks = []
        start = 0

        while start < len(words):
            end = start + chunk_size
            chunk = " ".join(words[start:end]).strip()
            if chunk:
                chunks.append(chunk)

            start += (chunk_size - overlap)

        return chunks
        
    def get_stats(self):
        """Get vector store statistics"""
        count = self.collection.count()
        return {
            'total_chunks': count,
            'collection_name': self.collection.name
        }
