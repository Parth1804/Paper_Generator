"""
User data management module.
Handles loading and saving of user-specific topics and papers.
"""

from typing import Dict, List, Optional, Any
from database import get_user_data, save_user_data, delete_user_data


class UserDataManager:
    """Manages user-specific data for topics and papers."""
    
    @staticmethod
    def load_topics(user_id: int) -> List[Dict[str, Any]]:
        """
        Load all topics for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of topics
        """
        data = get_user_data(user_id, 'topics')
        if not data:
            return []
        
        # Convert dict to list maintaining order
        topics = []
        for key, topic_data in data.items():
            topic_data['_key'] = key
            topics.append(topic_data)
        return topics
    
    @staticmethod
    def add_topic(user_id: int, topic_title: str) -> bool:
        """
        Add a new topic for user.
        
        Args:
            user_id: User ID
            topic_title: Topic title/name
            
        Returns:
            True if successful
        """
        topic_key = f"topic_{len(UserDataManager.load_topics(user_id)) + 1}_{int(__import__('time').time())}"
        topic_data = {
            'title': topic_title,
            'created_at': __import__('datetime').datetime.now().isoformat()
        }
        return save_user_data(user_id, 'topics', topic_key, topic_data)
    
    @staticmethod
    def delete_topic(user_id: int, topic_key: str) -> bool:
        """
        Delete a topic.
        
        Args:
            user_id: User ID
            topic_key: Topic key to delete
            
        Returns:
            True if successful
        """
        return delete_user_data(user_id, 'topics', topic_key)
    
    @staticmethod
    def load_papers(user_id: int) -> Dict[str, Any]:
        """
        Load all papers for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary of papers
        """
        papers = get_user_data(user_id, 'papers')
        return papers if papers else {}
    
    @staticmethod
    def save_paper(user_id: int, paper_key: str, paper_data: Dict[str, Any]) -> bool:
        """
        Save a paper for user.
        
        Args:
            user_id: User ID
            paper_key: Unique key for the paper (typically topic name)
            paper_data: Paper data dictionary
            
        Returns:
            True if successful
        """
        return save_user_data(user_id, 'papers', paper_key, paper_data)
    
    @staticmethod
    def delete_paper(user_id: int, paper_key: str) -> bool:
        """
        Delete a paper.
        
        Args:
            user_id: User ID
            paper_key: Paper key to delete
            
        Returns:
            True if successful
        """
        return delete_user_data(user_id, 'papers', paper_key)
    
    @staticmethod
    def get_paper(user_id: int, paper_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific paper.
        
        Args:
            user_id: User ID
            paper_key: Paper key
            
        Returns:
            Paper data or None
        """
        return get_user_data(user_id, 'papers', paper_key)
    
    @staticmethod
    def migrate_session_to_db(user_id: int, topics_list: List[Dict[str, Any]], papers_dict: Dict[str, Any]) -> bool:
        """
        Migrate session data to persistent database.
        Useful when user logs in.
        
        Args:
            user_id: User ID
            topics_list: List of topics from session state
            papers_dict: Dictionary of papers from session state
            
        Returns:
            True if successful
        """
        try:
            # Save topics
            for idx, topic in enumerate(topics_list):
                topic_key = f"topic_{idx}_{__import__('time').time()}"
                save_user_data(user_id, 'topics', topic_key, topic)
            
            # Save papers
            for paper_key, paper_data in papers_dict.items():
                save_user_data(user_id, 'papers', paper_key, paper_data)
            
            return True
        except Exception as e:
            print(f"Error migrating session data: {e}")
            return False
