"""
PubMed API client wrapper for biomedical literature search and retrieval
"""

import os
import logging
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import time
import json
from urllib.parse import quote

logger = logging.getLogger(__name__)


class PubMedClient:
    """Wrapper class for PubMed E-utilities API operations"""
    
    def __init__(self):
        """Initialize PubMed client with configuration"""
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.api_key = os.environ.get('PUBMED_API_KEY')
        self.email = os.environ.get('PUBMED_EMAIL', 'user@example.com')
        self.tool = os.environ.get('PUBMED_TOOL', 'ResearchPlatform')
        
        # Rate limiting: 3/sec without key, 10/sec with key
        self.rate_limit = 10 if self.api_key else 3
        self.last_request_time = 0
        
        # Default parameters
        self.default_retmax = 100  # Max results per request
        self.max_retmax = 10000    # PubMed's maximum
        
        logger.info(f"PubMed client initialized (API key: {'Yes' if self.api_key else 'No'})")
    
    def is_connected(self) -> bool:
        """Check if client can connect to PubMed"""
        try:
            # Test with a simple search
            response = self._make_request('esearch.fcgi', {
                'db': 'pubmed',
                'term': 'test',
                'retmax': 1
            })
            return response.status_code == 200
        except:
            return False
    
    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> requests.Response:
        """Make rate-limited request to PubMed API"""
        # Add authentication parameters
        params['email'] = self.email
        params['tool'] = self.tool
        if self.api_key:
            params['api_key'] = self.api_key
        
        # Rate limiting
        time_since_last = time.time() - self.last_request_time
        min_interval = 1.0 / self.rate_limit
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        
        # Make request
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, params=params)
        self.last_request_time = time.time()
        
        if response.status_code != 200:
            logger.error(f"PubMed API error: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        return response
    
    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
              max_results: int = 100) -> Dict[str, Any]:
        """
        Search PubMed with query and filters
        
        Args:
            query: Search query string
            filters: Dictionary of filters to apply
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary with search results and metadata
        """
        try:
            # Build query with filters
            full_query = self._build_query(query, filters)
            logger.info(f"Searching PubMed with query: {full_query}")
            
            # Search to get PMIDs
            search_params = {
                'db': 'pubmed',
                'term': full_query,
                'retmax': min(max_results, self.max_retmax),
                'retmode': 'json',
                'sort': filters.get('sort', 'relevance') if filters else 'relevance'
            }
            
            response = self._make_request('esearch.fcgi', search_params)
            search_data = response.json()
            
            # Extract results
            result = {
                'query': query,
                'full_query': full_query,
                'count': int(search_data['esearchresult'].get('count', 0)),
                'pmids': search_data['esearchresult'].get('idlist', []),
                'filters_applied': filters or {},
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Found {result['count']} results, retrieved {len(result['pmids'])} PMIDs")
            return result
            
        except Exception as e:
            logger.error(f"Error searching PubMed: {e}")
            raise
    
    def _build_query(self, base_query: str, filters: Optional[Dict[str, Any]]) -> str:
        """Build complete query string with filters"""
        query_parts = [base_query]
        
        if not filters:
            return base_query
        
        # Date range filter
        if 'date_from' in filters or 'date_to' in filters:
            date_from = filters.get('date_from', '1900/01/01')
            date_to = filters.get('date_to', datetime.now().strftime('%Y/%m/%d'))
            query_parts.append(f'("{date_from}"[PDAT] : "{date_to}"[PDAT])')
        
        # Publication type filters
        if 'publication_types' in filters:
            pub_types = filters['publication_types']
            if isinstance(pub_types, list):
                pub_type_query = ' OR '.join([f'{pt}[PT]' for pt in pub_types])
                query_parts.append(f'({pub_type_query})')
        
        # Language filter
        if 'languages' in filters:
            languages = filters['languages']
            if isinstance(languages, list):
                lang_query = ' OR '.join([f'{lang}[LA]' for lang in languages])
                query_parts.append(f'({lang_query})')
        
        # Journal filter
        if 'journals' in filters:
            journals = filters['journals']
            if isinstance(journals, list):
                journal_query = ' OR '.join([f'"{j}"[TA]' for j in journals])
                query_parts.append(f'({journal_query})')
        
        # MeSH terms
        if 'mesh_terms' in filters:
            mesh_terms = filters['mesh_terms']
            if isinstance(mesh_terms, list):
                mesh_query = ' OR '.join([f'"{term}"[MeSH]' for term in mesh_terms])
                query_parts.append(f'({mesh_query})')
        
        # Author filter
        if 'authors' in filters:
            authors = filters['authors']
            if isinstance(authors, list):
                author_query = ' OR '.join([f'"{author}"[AU]' for author in authors])
                query_parts.append(f'({author_query})')
        
        # Free text fields
        if 'title_abstract' in filters and filters['title_abstract']:
            query_parts.append('[TIAB]')
        
        # Combine all parts with AND
        return ' AND '.join(query_parts)
    
    def fetch_articles(self, pmids: List[str], 
                      include_abstract: bool = True,
                      include_full_text: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch full article details for given PMIDs
        
        Args:
            pmids: List of PubMed IDs
            include_abstract: Include abstract text
            include_full_text: Attempt to include full text links
            
        Returns:
            List of article dictionaries
        """
        if not pmids:
            return []
        
        articles = []
        
        try:
            # Process in batches of 200 (PubMed limit)
            batch_size = 200
            for i in range(0, len(pmids), batch_size):
                batch_pmids = pmids[i:i + batch_size]
                logger.info(f"Fetching batch {i//batch_size + 1}: {len(batch_pmids)} articles")
                
                # Fetch article data
                fetch_params = {
                    'db': 'pubmed',
                    'id': ','.join(batch_pmids),
                    'retmode': 'xml'
                }
                
                response = self._make_request('efetch.fcgi', fetch_params)
                
                # Parse XML response
                root = ET.fromstring(response.text)
                
                for article_elem in root.findall('.//PubmedArticle'):
                    article = self._parse_article_xml(article_elem, include_abstract)
                    
                    # Add full text links if requested
                    if include_full_text:
                        article['full_text_links'] = self._get_full_text_links(article['pmid'])
                    
                    articles.append(article)
            
            logger.info(f"Successfully fetched {len(articles)} articles")
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching articles: {e}")
            raise
    
    def _parse_article_xml(self, article_elem: ET.Element, 
                          include_abstract: bool = True) -> Dict[str, Any]:
        """Parse article XML element into dictionary"""
        article = {}
        
        try:
            # PMID
            pmid_elem = article_elem.find('.//PMID')
            article['pmid'] = pmid_elem.text if pmid_elem is not None else ''
            
            # Article metadata
            article_meta = article_elem.find('.//Article')
            if article_meta:
                # Title
                title_elem = article_meta.find('.//ArticleTitle')
                article['title'] = title_elem.text if title_elem is not None else ''
                
                # Abstract
                if include_abstract:
                    abstract_texts = []
                    for abstract_elem in article_meta.findall('.//AbstractText'):
                        label = abstract_elem.get('Label', '')
                        text = abstract_elem.text or ''
                        if label:
                            abstract_texts.append(f"{label}: {text}")
                        else:
                            abstract_texts.append(text)
                    article['abstract'] = '\n'.join(abstract_texts)
                
                # Authors
                authors = []
                for author in article_meta.findall('.//Author'):
                    last_name = author.find('LastName')
                    first_name = author.find('ForeName')
                    if last_name is not None:
                        name = last_name.text
                        if first_name is not None:
                            name = f"{name}, {first_name.text}"
                        authors.append(name)
                article['authors'] = authors
                
                # Journal info
                journal = article_meta.find('.//Journal')
                if journal:
                    title_elem = journal.find('.//Title')
                    article['journal'] = title_elem.text if title_elem is not None else ''
                    
                    # Publication date
                    pub_date = journal.find('.//PubDate')
                    if pub_date:
                        year = pub_date.find('Year')
                        month = pub_date.find('Month')
                        day = pub_date.find('Day')
                        
                        date_parts = []
                        if year is not None:
                            date_parts.append(year.text)
                        if month is not None:
                            date_parts.append(month.text)
                        if day is not None:
                            date_parts.append(day.text)
                        article['publication_date'] = ' '.join(date_parts)
                
                # Publication type
                pub_types = []
                for pub_type in article_meta.findall('.//PublicationType'):
                    if pub_type.text:
                        pub_types.append(pub_type.text)
                article['publication_types'] = pub_types
                
                # MeSH terms
                mesh_terms = []
                for mesh in article_elem.findall('.//MeshHeading/DescriptorName'):
                    if mesh.text:
                        mesh_terms.append(mesh.text)
                article['mesh_terms'] = mesh_terms
                
                # Keywords
                keywords = []
                for keyword in article_meta.findall('.//Keyword'):
                    if keyword.text:
                        keywords.append(keyword.text)
                article['keywords'] = keywords
                
                # DOI
                for article_id in article_elem.findall('.//ArticleId'):
                    if article_id.get('IdType') == 'doi':
                        article['doi'] = article_id.text
                        break
            
        except Exception as e:
            logger.error(f"Error parsing article XML: {e}")
        
        return article
    
    def _get_full_text_links(self, pmid: str) -> Dict[str, str]:
        """Get full text links for an article"""
        links = {}
        
        try:
            # Get links from elink
            params = {
                'db': 'pubmed',
                'id': pmid,
                'cmd': 'prlinks',
                'retmode': 'json'
            }
            
            response = self._make_request('elink.fcgi', params)
            data = response.json()
            
            # Parse link data
            if 'linksets' in data and data['linksets']:
                linkset = data['linksets'][0]
                if 'idurllist' in linkset and linkset['idurllist']:
                    urls = linkset['idurllist'][0].get('objurls', [])
                    for url_info in urls:
                        provider = url_info.get('provider', 'Unknown')
                        url = url_info.get('url', {}).get('value', '')
                        if url:
                            links[provider] = url
        
        except Exception as e:
            logger.warning(f"Could not fetch full text links for PMID {pmid}: {e}")
        
        return links
    
    def get_citations(self, pmid: str) -> Dict[str, Any]:
        """Get citation information for an article"""
        try:
            # Get citing articles
            params = {
                'db': 'pubmed',
                'id': pmid,
                'linkname': 'pubmed_pubmed_citedin',
                'retmode': 'json'
            }
            
            response = self._make_request('elink.fcgi', params)
            data = response.json()
            
            citations = {
                'pmid': pmid,
                'cited_by_pmids': [],
                'citation_count': 0
            }
            
            if 'linksets' in data and data['linksets']:
                for linkset in data['linksets']:
                    if 'linksetdbs' in linkset:
                        for db in linkset['linksetdbs']:
                            if db.get('linkname') == 'pubmed_pubmed_citedin':
                                citations['cited_by_pmids'] = db.get('links', [])
                                citations['citation_count'] = len(citations['cited_by_pmids'])
                                break
            
            return citations
            
        except Exception as e:
            logger.error(f"Error fetching citations for PMID {pmid}: {e}")
            raise
    
    def get_related_articles(self, pmid: str, max_related: int = 10) -> List[str]:
        """Get related articles for a given PMID"""
        try:
            params = {
                'db': 'pubmed',
                'id': pmid,
                'linkname': 'pubmed_pubmed',
                'retmode': 'json',
                'retmax': max_related
            }
            
            response = self._make_request('elink.fcgi', params)
            data = response.json()
            
            related_pmids = []
            if 'linksets' in data and data['linksets']:
                for linkset in data['linksets']:
                    if 'linksetdbs' in linkset:
                        for db in linkset['linksetdbs']:
                            if db.get('linkname') == 'pubmed_pubmed':
                                related_pmids = db.get('links', [])[:max_related]
                                break
            
            return related_pmids
            
        except Exception as e:
            logger.error(f"Error fetching related articles for PMID {pmid}: {e}")
            raise
    
    def advanced_search(self, 
                       keywords: Optional[List[str]] = None,
                       title_words: Optional[List[str]] = None,
                       abstract_words: Optional[List[str]] = None,
                       authors: Optional[List[str]] = None,
                       journals: Optional[List[str]] = None,
                       mesh_terms: Optional[List[str]] = None,
                       date_from: Optional[str] = None,
                       date_to: Optional[str] = None,
                       publication_types: Optional[List[str]] = None,
                       max_results: int = 100) -> Dict[str, Any]:
        """
        Perform advanced search with multiple field-specific criteria
        
        Args:
            Various search criteria by field
            
        Returns:
            Search results dictionary
        """
        query_parts = []
        
        # Build query from components
        if keywords:
            query_parts.append(' OR '.join([f'"{kw}"[All Fields]' for kw in keywords]))
        
        if title_words:
            query_parts.append(' AND '.join([f'"{word}"[TI]' for word in title_words]))
        
        if abstract_words:
            query_parts.append(' AND '.join([f'"{word}"[AB]' for word in abstract_words]))
        
        if authors:
            author_query = ' OR '.join([f'"{author}"[AU]' for author in authors])
            query_parts.append(f'({author_query})')
        
        if journals:
            journal_query = ' OR '.join([f'"{journal}"[TA]' for journal in journals])
            query_parts.append(f'({journal_query})')
        
        if mesh_terms:
            mesh_query = ' OR '.join([f'"{term}"[MeSH Major Topic]' for term in mesh_terms])
            query_parts.append(f'({mesh_query})')
        
        # Date range
        if date_from or date_to:
            from_date = date_from or '1900/01/01'
            to_date = date_to or datetime.now().strftime('%Y/%m/%d')
            query_parts.append(f'("{from_date}"[PDAT] : "{to_date}"[PDAT])')
        
        # Publication types
        if publication_types:
            pub_query = ' OR '.join([f'"{pt}"[PT]' for pt in publication_types])
            query_parts.append(f'({pub_query})')
        
        # Combine query parts
        full_query = ' AND '.join(query_parts) if query_parts else '*'
        
        # Perform search
        return self.search(full_query, max_results=max_results)
    
    def filter_articles_local(self, articles: List[Dict[str, Any]], 
                            criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Filter articles locally after download
        
        Args:
            articles: List of article dictionaries
            criteria: Filtering criteria
            
        Returns:
            Filtered list of articles
        """
        filtered = []
        
        for article in articles:
            # Check each criterion
            include = True
            
            # Keyword filter in title/abstract
            if 'keywords' in criteria:
                keywords = criteria['keywords']
                text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
                if not any(kw.lower() in text for kw in keywords):
                    include = False
            
            # Author filter
            if include and 'authors' in criteria:
                article_authors = [a.lower() for a in article.get('authors', [])]
                if not any(auth.lower() in ' '.join(article_authors) 
                          for auth in criteria['authors']):
                    include = False
            
            # Journal filter
            if include and 'journals' in criteria:
                article_journal = article.get('journal', '').lower()
                if not any(j.lower() in article_journal for j in criteria['journals']):
                    include = False
            
            # Publication type filter
            if include and 'publication_types' in criteria:
                article_types = [pt.lower() for pt in article.get('publication_types', [])]
                if not any(pt.lower() in article_types for pt in criteria['publication_types']):
                    include = False
            
            # Year filter
            if include and 'year_from' in criteria:
                pub_date = article.get('publication_date', '')
                try:
                    year = int(pub_date.split()[0]) if pub_date else 0
                    if year < criteria['year_from']:
                        include = False
                except:
                    pass
            
            if include and 'year_to' in criteria:
                pub_date = article.get('publication_date', '')
                try:
                    year = int(pub_date.split()[0]) if pub_date else 9999
                    if year > criteria['year_to']:
                        include = False
                except:
                    pass
            
            # Citation count filter (would need separate API calls)
            # Impact factor filter (would need journal database)
            
            if include:
                filtered.append(article)
        
        logger.info(f"Filtered {len(articles)} articles to {len(filtered)} based on local criteria")
        return filtered
    
    def save_articles(self, articles: List[Dict[str, Any]], 
                     filepath: str, format: str = 'json') -> None:
        """
        Save articles to file
        
        Args:
            articles: List of article dictionaries
            filepath: Output file path
            format: Output format (json, csv, bibtex)
        """
        try:
            if format == 'json':
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(articles, f, indent=2, ensure_ascii=False)
            
            elif format == 'csv':
                import csv
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    if articles:
                        # Use first article to get field names
                        fieldnames = ['pmid', 'title', 'authors', 'journal', 
                                    'publication_date', 'abstract', 'doi']
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        
                        for article in articles:
                            row = {k: article.get(k, '') for k in fieldnames}
                            # Convert lists to strings
                            if isinstance(row['authors'], list):
                                row['authors'] = '; '.join(row['authors'])
                            writer.writerow(row)
            
            elif format == 'bibtex':
                with open(filepath, 'w', encoding='utf-8') as f:
                    for article in articles:
                        bibtex = self._to_bibtex(article)
                        f.write(bibtex + '\n\n')
            
            logger.info(f"Saved {len(articles)} articles to {filepath} as {format}")
            
        except Exception as e:
            logger.error(f"Error saving articles: {e}")
            raise
    
    def _to_bibtex(self, article: Dict[str, Any]) -> str:
        """Convert article to BibTeX format"""
        pmid = article.get('pmid', 'unknown')
        
        # Determine entry type
        pub_types = article.get('publication_types', [])
        if 'Review' in pub_types:
            entry_type = 'article'
        elif 'Clinical Trial' in pub_types:
            entry_type = 'article'
        else:
            entry_type = 'article'
        
        # Build BibTeX entry
        bibtex = f"@{entry_type}{{{pmid},\n"
        
        if article.get('title'):
            bibtex += f"  title = {{{article['title']}}},\n"
        
        if article.get('authors'):
            authors_str = ' and '.join(article['authors'])
            bibtex += f"  author = {{{authors_str}}},\n"
        
        if article.get('journal'):
            bibtex += f"  journal = {{{article['journal']}}},\n"
        
        if article.get('publication_date'):
            # Try to extract year
            pub_date = article['publication_date']
            year = pub_date.split()[0] if pub_date else ''
            if year:
                bibtex += f"  year = {{{year}}},\n"
        
        if article.get('doi'):
            bibtex += f"  doi = {{{article['doi']}}},\n"
        
        bibtex += f"  pmid = {{{pmid}}}\n"
        bibtex += "}"
        
        return bibtex
