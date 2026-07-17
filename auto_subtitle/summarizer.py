import os
import openai
from datetime import datetime
from typing import Dict, Any, Optional

class SubtitleSummarizer:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        """
        Initialize the subtitle summarizer with OpenAI API.
        
        Args:
            api_key: OpenAI API key (default: None, will use OPENAI_API_KEY env variable)
            model: OpenAI model to use (default: gpt-3.5-turbo)
        """
        # Use provided API key or get from environment variable
        if api_key:
            openai.api_key = api_key
        else:
            openai.api_key = os.environ.get("OPENAI_API_KEY")
            
            if not openai.api_key:
                raise ValueError(
                    "OpenAI API key is required. Either pass it as api_key or set OPENAI_API_KEY environment variable."
                )
        
        self.model = model
    
    def parse_srt(self, srt_file: str) -> str:
        """
        Parse an SRT file and extract the text content.
        
        Args:
            srt_file: Path to the SRT file
            
        Returns:
            A string containing all the text from the subtitles
        """
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by subtitle entries (double newline)
        entries = content.strip().split('\n\n')
        
        # Extract only the text parts (ignoring index and timestamps)
        texts = []
        for entry in entries:
            lines = entry.split('\n')
            if len(lines) >= 3:  # Valid entry has at least 3 lines (index, timestamp, text)
                # Join all lines after the timestamp (in case text spans multiple lines)
                text = '\n'.join(lines[2:])
                texts.append(text)
        
        return ' '.join(texts)
    
    def summarize(self, srt_file: str, output_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Summarize the content of an SRT file using OpenAI API.
        
        Args:
            srt_file: Path to the SRT file
            output_file: Path to save the summary (default: None)
            
        Returns:
            A dictionary containing the summary and other information
        """
        # Extract text from SRT file
        transcript = self.parse_srt(srt_file)

        # Keep the prompt within the model's context window (~4 chars per token)
        max_chars = 40000
        if len(transcript) > max_chars:
            print(f"Warning: transcript is long ({len(transcript)} chars); "
                  f"truncating to {max_chars} chars for summarization.")
            transcript = transcript[:max_chars]

        # Prepare the prompt for OpenAI
        prompt = f"""
        You are an AI assistant that creates concise meeting minutes from transcripts.
        
        Please analyze the following transcript and create professional meeting minutes that include:
        1. A brief executive summary (2-3 sentences)
        2. Key discussion points
        3. Decisions made
        4. Action items with assigned responsibilities (if mentioned)
        5. Any important deadlines or dates mentioned
        
        Format the output in a clean, professional manner suitable for business documentation.
        
        Here is the transcript:
        {transcript}
        """
        
        # Call OpenAI API
        response = openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a professional assistant that creates concise, well-structured meeting minutes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        # Extract the summary
        summary = response.choices[0].message.content.strip()
        
        # Prepare the result
        result = {
            "summary": summary,
            "transcript": transcript,
            "model": self.model,
            "source_file": srt_file
        }
        
        # Save to file if output_file is provided
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            print(f"Summary saved to {output_file}")
        
        return result
    
    def summarize_to_markdown(self, srt_file: str, output_file: Optional[str] = None) -> str:
        """
        Summarize the content of an SRT file and format as Markdown.
        
        Args:
            srt_file: Path to the SRT file
            output_file: Path to save the Markdown summary (default: None)
            
        Returns:
            A string containing the Markdown-formatted summary
        """
        # Get the summary
        result = self.summarize(srt_file)
        summary = result["summary"]
        
        # Format as Markdown
        filename = os.path.basename(srt_file)
        timestamp = datetime.fromtimestamp(
            os.path.getmtime(srt_file)).strftime("%Y-%m-%d %H:%M")
        
        markdown = f"""# Meeting Minutes

## Source
- Transcript: {filename}
- Date: {timestamp}

{summary}

---
*Generated by Auto-Subtitle AI Summarizer*
"""
        
        # Save to file if output_file is provided
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(markdown)
            
            print(f"Markdown summary saved to {output_file}")
        
        return markdown 