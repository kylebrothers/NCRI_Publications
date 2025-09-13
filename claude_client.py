"""
Claude API client wrapper for AI text generation and analysis
"""

import os
import logging
import anthropic
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Wrapper class for Claude API operations"""
    
    def __init__(self):
        """Initialize Claude client with environment credentials"""
        self.client = None
        self.api_key = os.environ.get('CLAUDE_API_KEY')
        self.model = os.environ.get('CLAUDE_MODEL', 'claude-3-sonnet-20240229')
        self.max_tokens = int(os.environ.get('CLAUDE_MAX_TOKENS', '4000'))
        
        if self.api_key and self.api_key != 'your_claude_api_key_here':
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info(f"Claude client initialized with model: {self.model}")
                
                # Test the connection with a minimal call
                self._test_connection()
            except Exception as e:
                logger.error(f"Failed to initialize Claude client: {e}")
                self.client = None
        else:
            logger.warning("No Claude API key provided or using placeholder")
    
    def _test_connection(self):
        """Test the API connection with a minimal request"""
        try:
            # Very short test to verify API key works
            message = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            logger.info("Claude API connection verified")
        except Exception as e:
            logger.error(f"Claude API connection test failed: {e}")
            self.client = None
            raise
    
    def is_connected(self) -> bool:
        """Check if client is connected to Claude API"""
        return self.client is not None
    
    def generate(self, prompt: str, context: Optional[str] = None, 
                 system_prompt: Optional[str] = None,
                 temperature: float = 0.7,
                 max_tokens: Optional[int] = None) -> str:
        """
        Generate text using Claude
        
        Args:
            prompt: The user's prompt/question
            context: Optional context (documents, data, etc.)
            system_prompt: Optional system instructions
            temperature: Creativity parameter (0-1)
            max_tokens: Override default max tokens
            
        Returns:
            Generated text response
        """
        if not self.is_connected():
            raise Exception("Claude client not connected")
        
        try:
            # Build the user message
            user_message = prompt
            if context:
                user_message = f"Context:\n{context}\n\nRequest:\n{prompt}"
            
            # Build messages array
            messages = [{"role": "user", "content": user_message}]
            
            # Build request parameters
            params = {
                "model": self.model,
                "max_tokens": max_tokens or self.max_tokens,
                "messages": messages,
                "temperature": temperature
            }
            
            # Add system prompt if provided
            if system_prompt:
                params["system"] = system_prompt
            
            # Make API call
            logger.info(f"Calling Claude API with {len(user_message)} character prompt")
            message = self.client.messages.create(**params)
            
            # Extract response text
            response_text = message.content[0].text
            logger.info(f"Claude generated {len(response_text)} characters")
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating text with Claude: {e}")
            raise
    
    def analyze(self, text: str, analysis_type: str = "summary",
                custom_instructions: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze text using Claude
        
        Args:
            text: Text to analyze
            analysis_type: Type of analysis (summary, sentiment, themes, etc.)
            custom_instructions: Optional custom analysis instructions
            
        Returns:
            Analysis results as dictionary
        """
        if not self.is_connected():
            raise Exception("Claude client not connected")
        
        try:
            # Build analysis prompt based on type
            analysis_prompts = {
                "summary": "Please provide a concise summary of the following text, highlighting key points:",
                "sentiment": "Analyze the sentiment and tone of the following text. Provide scores for: positive, negative, neutral, and identify emotional themes:",
                "themes": "Identify and list the main themes, topics, and concepts in the following text:",
                "key_points": "Extract the key points and important information from the following text as a bulleted list:",
                "entities": "Identify and categorize all named entities (people, organizations, locations, dates, etc.) in the following text:",
                "questions": "Generate relevant research questions based on the following text:",
                "critique": "Provide a critical analysis of the arguments, evidence, and logic in the following text:"
            }
            
            # Get base prompt or use custom
            if custom_instructions:
                prompt = custom_instructions
            else:
                prompt = analysis_prompts.get(analysis_type, analysis_prompts["summary"])
            
            # Add text to analyze
            full_prompt = f"{prompt}\n\nText to analyze:\n{text}"
            
            # Add JSON formatting instruction for structured output
            if analysis_type != "summary":
                full_prompt += "\n\nProvide your analysis in a structured format with clear sections."
            
            # Generate analysis
            response = self.generate(
                prompt=full_prompt,
                temperature=0.3  # Lower temperature for analysis tasks
            )
            
            # Parse response into structured format
            result = {
                "analysis_type": analysis_type,
                "timestamp": datetime.now().isoformat(),
                "content": response,
                "text_length": len(text),
                "model_used": self.model
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing text with Claude: {e}")
            raise
    
    def compare_texts(self, text1: str, text2: str, 
                      comparison_type: str = "differences") -> Dict[str, Any]:
        """
        Compare two texts using Claude
        
        Args:
            text1: First text
            text2: Second text  
            comparison_type: Type of comparison (differences, similarities, both)
            
        Returns:
            Comparison results
        """
        if not self.is_connected():
            raise Exception("Claude client not connected")
        
        try:
            prompts = {
                "differences": "Compare these two texts and highlight the key differences:",
                "similarities": "Compare these two texts and identify the similarities and common themes:",
                "both": "Provide a detailed comparison of these two texts, noting both similarities and differences:",
                "factual": "Compare the factual claims in these two texts and identify any contradictions or agreements:"
            }
            
            prompt = prompts.get(comparison_type, prompts["both"])
            
            full_prompt = f"{prompt}\n\nText 1:\n{text1}\n\nText 2:\n{text2}"
            
            response = self.generate(
                prompt=full_prompt,
                temperature=0.3
            )
            
            return {
                "comparison_type": comparison_type,
                "timestamp": datetime.now().isoformat(),
                "analysis": response,
                "text1_length": len(text1),
                "text2_length": len(text2)
            }
            
        except Exception as e:
            logger.error(f"Error comparing texts with Claude: {e}")
            raise
    
    def extract_structured_data(self, text: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured data from text according to a schema
        
        Args:
            text: Source text
            schema: Dictionary describing desired output structure
            
        Returns:
            Extracted data matching schema
        """
        if not self.is_connected():
            raise Exception("Claude client not connected")
        
        try:
            import json
            
            prompt = f"""Extract information from the text according to this schema:
{json.dumps(schema, indent=2)}

Return the extracted data as valid JSON matching the schema structure.
Only include information explicitly stated in the text.

Text to process:
{text}

Extracted JSON:"""
            
            response = self.generate(
                prompt=prompt,
                temperature=0.1  # Very low temperature for structured extraction
            )
            
            # Try to parse as JSON
            try:
                # Find JSON in response (it might have explanation text around it)
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    extracted_data = json.loads(json_match.group())
                else:
                    # Fallback: try to parse entire response
                    extracted_data = json.loads(response)
            except json.JSONDecodeError:
                logger.warning("Could not parse Claude response as JSON, returning raw text")
                extracted_data = {"raw_response": response}
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error extracting structured data with Claude: {e}")
            raise
    
    def generate_questions(self, text: str, question_type: str = "research",
                          num_questions: int = 5) -> List[str]:
        """
        Generate questions based on text
        
        Args:
            text: Source text
            question_type: Type of questions (research, comprehension, critical)
            num_questions: Number of questions to generate
            
        Returns:
            List of generated questions
        """
        if not self.is_connected():
            raise Exception("Claude client not connected")
        
        try:
            question_prompts = {
                "research": f"Generate {num_questions} research questions that could be explored based on this text:",
                "comprehension": f"Generate {num_questions} comprehension questions to test understanding of this text:",
                "critical": f"Generate {num_questions} critical thinking questions that challenge the assumptions in this text:",
                "followup": f"Generate {num_questions} follow-up questions for further investigation based on this text:"
            }
            
            prompt = question_prompts.get(question_type, question_prompts["research"])
            full_prompt = f"{prompt}\n\n{text}\n\nQuestions (one per line):"
            
            response = self.generate(
                prompt=full_prompt,
                temperature=0.8  # Higher temperature for creative question generation
            )
            
            # Parse questions from response
            questions = []
            for line in response.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Remove numbering if present
                    import re
                    line = re.sub(r'^\d+[\.\)]\s*', '', line)
                    if line:
                        questions.append(line)
            
            return questions[:num_questions]
            
        except Exception as e:
            logger.error(f"Error generating questions with Claude: {e}")
            raise
    
    def batch_process(self, items: List[Dict[str, Any]], 
                      operation: str = "summarize",
                      batch_size: int = 5) -> List[Dict[str, Any]]:
        """
        Process multiple items in batches
        
        Args:
            items: List of items to process
            operation: Operation to perform on each item
            batch_size: Number of items to process at once
            
        Returns:
            List of processed results
        """
        if not self.is_connected():
            raise Exception("Claude client not connected")
        
        results = []
        
        try:
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1} of {len(items)//batch_size + 1}")
                
                for item in batch:
                    if operation == "summarize":
                        result = self.analyze(item.get('text', ''), 'summary')
                    elif operation == "extract":
                        result = self.extract_structured_data(
                            item.get('text', ''),
                            item.get('schema', {})
                        )
                    else:
                        result = {"error": f"Unknown operation: {operation}"}
                    
                    result['item_id'] = item.get('id', f"item_{i}")
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch processing with Claude: {e}")
            raise
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model configuration"""
        return {
            "connected": self.is_connected(),
            "model": self.model,
            "max_tokens": self.max_tokens,
            "api_key_configured": bool(self.api_key and self.api_key != 'your_claude_api_key_here')
        }
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation)
        Claude uses ~1 token per 4 characters on average
        """
        return len(text) // 4
    
    def check_token_limit(self, text: str, limit: Optional[int] = None) -> bool:
        """Check if text is within token limits"""
        estimated_tokens = self.estimate_tokens(text)
        max_allowed = limit or self.max_tokens
        return estimated_tokens <= max_allowed
