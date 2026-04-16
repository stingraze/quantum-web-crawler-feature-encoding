import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from qiskit import QuantumCircuit, transpile
from qiskit.visualization import plot_histogram
from qiskit_aer import Aer
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Tuple, Set
import warnings
import sys

warnings.filterwarnings('ignore', category=UserWarning)

class RealWebGraphQuantumAnalyzer:
    def __init__(self, starting_url: str, max_pages: int = 20):
        self.starting_url = starting_url
        self.max_pages = max_pages
        self.graph = nx.DiGraph()
        self.url_to_id = {}
        self.id_to_url = {}
        self.server_info = {
            'traffic_load': {},
            'response_time': {},
            'quantum_path_prob': {},
            'page_size': {},
            'link_density': {}
        }
        self.graph_update = True
        
    def fetch_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse a web page"""
        try:
            response = requests.get(url, timeout=5, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; WebGraphAnalyzer/1.0)'
            })
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract all links from a page"""
        if not soup:
            return []
        
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(base_url, href)
            
            # Filter to same domain and valid URLs
            if self.is_valid_url(absolute_url):
                links.append(absolute_url)
                
        return list(set(links))  # Remove duplicates
    
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and from same domain"""
        try:
            parsed = urlparse(url)
            base_parsed = urlparse(self.starting_url)
            return (parsed.scheme in ['http', 'https'] and 
                   parsed.netloc == base_parsed.netloc)
        except:
            return False
    
    def crawl_website(self) -> None:
        """Crawl the website to build the graph"""
        print(f"Starting crawl from: {self.starting_url}")
        
        queue = [self.starting_url]
        visited = set()
        node_id = 0
        
        while queue and len(visited) < self.max_pages:
            current_url = queue.pop(0)
            if current_url in visited:
                continue
                
            print(f"Crawling: {current_url}")
            visited.add(current_url)
            
            # Assign ID to URL
            if current_url not in self.url_to_id:
                # Failsafe: Don't exceed max_pages
                if len(self.url_to_id) >= self.max_pages:
                    continue
                self.url_to_id[current_url] = node_id
                self.id_to_url[node_id] = current_url
                self.graph.add_node(node_id)
                node_id += 1
            
            # Fetch and parse page
            soup = self.fetch_page(current_url)
            if not soup:
                continue
            
            # Extract page features
            self.analyze_page_features(current_url, soup)
            
            # Extract and process links
            links = self.extract_links(soup, current_url)
            current_id = self.url_to_id[current_url]
            
            for link in links:
                if link not in self.url_to_id:
                    # STRICT QUBIT LIMIT FIX:
                    # Stop adding new nodes/qubits to the graph if we hit the limit
                    if len(self.url_to_id) >= self.max_pages:
                        continue
                        
                    self.url_to_id[link] = node_id
                    self.id_to_url[node_id] = link
                    self.graph.add_node(node_id)
                    node_id += 1
                
                # Only add edges if the link actually made it into the graph
                if link in self.url_to_id:
                    link_id = self.url_to_id[link]
                    # Prevent self-loops (which cause the duplicate qubit argument error)
                    if current_id != link_id:
                        self.graph.add_edge(current_id, link_id)
                
                # Add to queue if not visited and under limit
                if link not in visited and len(visited) < self.max_pages:
                    queue.append(link)
        
        print(f"Crawling completed. Found {len(self.graph.nodes())} nodes (qubits).")
    
    def analyze_page_features(self, url: str, soup: BeautifulSoup) -> None:
        """Analyze page features for quantum weighting"""
        url_id = self.url_to_id[url]
        
        # Page size (approx)
        page_size = len(str(soup))
        self.server_info['page_size'][url_id] = page_size
        
        # Link density
        links = soup.find_all('a', href=True)
        text_elements = soup.find_all(['p', 'div', 'span', 'h1', 'h2', 'h3'])
        total_text_length = sum(len(elem.get_text()) for elem in text_elements)
        
        link_density = len(links) / max(total_text_length, 1)
        self.server_info['link_density'][url_id] = link_density
        
        # Simulated traffic and response time (would be real metrics in production)
        self.server_info['traffic_load'][url_id] = np.random.random()
        self.server_info['response_time'][url_id] = np.random.random() * 100
    
    def Get_All_Connection(self) -> List[Tuple[int, int]]:
        """Get all connections/edges in the web graph"""
        return list(self.graph.edges())
    
    def Get_All_Website_Features(self) -> Dict[str, np.ndarray]:
        """Extract features for quantum analysis from real website data"""
        if len(self.graph.nodes()) == 0:
            return {}
            
        features = {}
        
        # Graph-based features
        if nx.is_directed(self.graph):
            features['in_degree'] = np.array([d for n, d in self.graph.in_degree()])
            features['out_degree'] = np.array([d for n, d in self.graph.out_degree()])
        else:
            degrees = np.array([d for n, d in self.graph.degree()])
            features['degree'] = degrees
        
        # Content-based features from Beautiful Soup analysis
        page_sizes = [self.server_info['page_size'].get(n, 0) for n in self.graph.nodes()]
        features['page_size'] = np.array(page_sizes)
        
        link_densities = [self.server_info['link_density'].get(n, 0) for n in self.graph.nodes()]
        features['link_density'] = np.array(link_densities)
        
        return features
    
    def Create_Quantum_Path_Circuit(self, start_node: int = 0) -> QuantumCircuit:
        """Create quantum circuit for path traversal simulation using real web data"""
        num_qubits = len(self.graph.nodes())
        if num_qubits == 0:
            return QuantumCircuit(1)  # Fallback empty circuit
            
        qc = QuantumCircuit(num_qubits)
        
        # Initialize superposition for exploring all pages
        qc.h(range(num_qubits))
        
        # Apply quantum operations based on real web graph structure
        for edge in self.Get_All_Connection():
            control, target = edge
            # Check that qubits are within bounds AND not identical (no self-loops)
            if control < num_qubits and target < num_qubits and control != target:
                qc.cx(control, target)
        
        # Amplify paths based on website features from Beautiful Soup
        features = self.Get_All_Website_Features()
        # Amplify paths based on website features from Beautiful Soup
        features = self.Get_All_Website_Features()
        if features:
            # Combine features for weighting
            if 'in_degree' in features and 'out_degree' in features:
                weights = features['in_degree'] + features['out_degree']
            elif 'degree' in features:
                weights = features['degree']
            else:
                weights = np.ones(num_qubits)
            
            # Convert the array to float to avoid casting errors
            weights = weights.astype(float)
            
            # Add content-based weights safely
            weights += features.get('page_size', np.zeros(num_qubits)) / 1000
            weights += features.get('link_density', np.zeros(num_qubits)) * 10
        
        # Measurement
        qc.measure_all()
        return qc
    
    def Calculate_Simulated_Path_Traversal(self, shots: int = 1024) -> Dict[int, float]:
        """Simulate quantum path traversal on real website data"""
        if len(self.graph.nodes()) == 0:
            return {}
            
        qc = self.Create_Quantum_Path_Circuit()
        simulator = Aer.get_backend('qasm_simulator')
        
        # Qiskit 1.0+ execution workflow: Transpile -> Run
        transpiled_circuit = transpile(qc, simulator)
        job = simulator.run(transpiled_circuit, shots=shots)
        result = job.result()
        counts = result.get_counts()
        
        # Convert to node probabilities
        node_probs = {}
        for bitstring, count in counts.items():
            # Reverse bitstring to match qubit order
            reversed_bits = bitstring[::-1]
            for i, bit in enumerate(reversed_bits):
                if i < len(self.graph.nodes()) and bit == '1':
                    node_probs[i] = node_probs.get(i, 0) + count
        
        # Normalize probabilities
        total = sum(node_probs.values())
        if total > 0:
            for node in node_probs:
                node_probs[node] /= total
            
        return node_probs
    
    def Server_Info_Update_and_Visualize(self, quantum_probs: Dict[int, float]):
        """Update server info and create visualization with real website data"""
        if len(self.graph.nodes()) == 0:
            print("No website data available for visualization")
            return
            
        # Update quantum path probabilities
        for node, prob in quantum_probs.items():
            self.server_info['quantum_path_prob'][node] = prob
        
        # Create visualization
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. GRAPH FIX: Spread out the nodes
        # Using kamada_kawai_layout or tweaking spring_layout(k=0.5) helps untangle central nodes
        try:
            pos = nx.kamada_kawai_layout(self.graph)
        except:
            # Fallback if kamada_kawai fails (e.g., disconnected graph)
            pos = nx.spring_layout(self.graph, k=0.5, iterations=50) 
            
        node_colors = [quantum_probs.get(node, 0.1) for node in self.graph.nodes()]
        
        nx.draw(self.graph, pos, ax=ax1, with_labels=True, 
                node_color=node_colors, cmap='viridis', 
                node_size=400, font_size=9, font_color='white', arrows=True)
        ax1.set_title('Website Link Structure (Quantum Path Probabilities)', pad=15)
        
        # Helper variables for plots
        nodes = list(self.graph.nodes())
        x_positions = range(len(nodes))
        x_labels = [f'Page {i}' for i in nodes]
        
        # 2. LABEL ALIGNMENT FIX: Add ha='right' to all rotated labels
        
        # Page features visualization
        page_sizes = [self.server_info['page_size'].get(n, 0) for n in nodes]
        ax2.bar(x_positions, page_sizes, alpha=0.7)
        ax2.set_title('Page Sizes (bytes)')
        ax2.set_xticks(x_positions)
        ax2.set_xticklabels(x_labels, rotation=45, ha='right')
        
        # Link density
        link_densities = [self.server_info['link_density'].get(n, 0) for n in nodes]
        ax3.bar(x_positions, link_densities, color='orange', alpha=0.7)
        ax3.set_title('Link Density (links per character)')
        ax3.set_xticks(x_positions)
        ax3.set_xticklabels(x_labels, rotation=45, ha='right')
        
        # Quantum path probabilities
        quantum_probs_list = [quantum_probs.get(n, 0) for n in nodes]
        ax4.bar(x_positions, quantum_probs_list, color='green', alpha=0.7)
        ax4.set_title('Quantum Path Traversal Probabilities')
        ax4.set_ylabel('Probability')
        ax4.set_xticks(x_positions)
        ax4.set_xticklabels(x_labels, rotation=45, ha='right')
        
        # 3. OVERLAP FIX: Force extra padding between subplots
        plt.tight_layout(pad=3.0, h_pad=4.0, w_pad=2.0)
        plt.show()
        
        # ... (keep your existing print statements below this) ...        
        # Print detailed summary
        print("\n=== Website Analysis Summary ===")
        print(f"Total pages crawled: {len(self.graph.nodes())}")
        print(f"Total links found: {len(self.Get_All_Connection())}")
        
        if quantum_probs:
            most_probable = max(quantum_probs, key=quantum_probs.get)
            print(f"Most probable quantum path: Page {most_probable}")
            print(f"URL: {self.id_to_url.get(most_probable, 'Unknown')}")
            print(f"Probability: {quantum_probs[most_probable]:.3f}")
        
        # Show top 3 most probable pages
        sorted_probs = sorted(quantum_probs.items(), key=lambda x: x[1], reverse=True)[:3]
        print("\nTop 3 most probable pages:")
        for node, prob in sorted_probs:
            url = self.id_to_url.get(node, f"Page {node}")
            print(f"  {url}: {prob:.3f}")
    
    def run_continuous_analysis(self, iterations: int = 3):
        """Run the complete analysis loop with real website data"""
        # First, crawl the website to get real data
        self.crawl_website()
        
        for i in range(iterations):
            if not self.graph_update:
                break
                
            print(f"\n--- Analysis Iteration {i+1} ---")
            
            # Get current connections
            connections = self.Get_All_Connection()
            print(f"Active links between pages: {len(connections)}")
            
            # Get website features from Beautiful Soup analysis
            features = self.Get_All_Website_Features()
            if features:
                avg_page_size = np.mean(features.get('page_size', [0]))
                print(f"Average page size: {avg_page_size:.0f} bytes")
            
            # Calculate quantum path traversal
            quantum_probs = self.Calculate_Simulated_Path_Traversal()
            
            # Update and visualize
            self.Server_Info_Update_and_Visualize(quantum_probs)
            
            # Simulate dynamic updates (in real scenario, this would re-crawl)
            if i < iterations - 1:  # Don't update after last iteration
                print("Simulating website updates...")
                time.sleep(2)

# Example usage with a real website
if __name__ == "__main__":
    # Ensure a valid URL is passed or fallback to a default
    url_input = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    
    analyzer = RealWebGraphQuantumAnalyzer(
        starting_url=url_input,  
        max_pages=10
    )
    
    analyzer.run_continuous_analysis(iterations=2)
