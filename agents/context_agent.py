"""
Context Agent - Manages RAG (Retrieval-Augmented Generation) across all meetings
"""
from typing import List, Dict, Optional
from rag.vector_store import VectorStore
from agents.summary_agent import SummaryAgent
import config.settings as settings

class ContextAgent:
    """Agent for context-aware question answering across multiple meetings"""
    
    def __init__(self, vector_store: Optional[VectorStore] = None, summary_agent: Optional[SummaryAgent] = None):
        """Initialize with vector store and summary agent"""
        self.vector_store = vector_store or VectorStore()
        self.summary_agent = summary_agent or SummaryAgent()
        print("✓ Context Agent initialized")
    
    def answer_global_question(self, question: str, max_context_chunks: int = 5) -> str:
        """
        Answer a question by retrieving context from multiple past meetings
        
        Args:
            question: User's question
            max_context_chunks: Number of relevant chunks to retrieve
            
        Returns:
            str: AI-generated answer based on retrieved context
        """
        # Step 1: Retrieve relevant chunks from vector store
        context = self.vector_store.get_relevant_context(question, max_chunks=max_context_chunks)
        
        if not context:
            return "I couldn't find any relevant information in the past meetings to answer your question."
        
        # Step 2: Use summary agent to generate an answer based on this context
        # We wrap the context with a header to tell the LLM it's from multiple meetings
        enhanced_context = f"INFORMATION RETRIEVED FROM PAST MEETINGS:\n\n{context}"
        
        answer = self.summary_agent.answer_question(
            transcript=enhanced_context,
            question=question
        )
        
        return answer

    def search_meetings(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        Perform semantic search across meetings
        
        Args:
            query: Search query
            n_results: Number of results to return
            
        Returns:
            List[Dict]: Search results with document content and metadata
        """
        results = self.vector_store.search_meetings(query, n_results=n_results)
        
        formatted_results = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                formatted_results.append({
                    'content': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'id': results['ids'][0][i]
                })
        
        return formatted_results
