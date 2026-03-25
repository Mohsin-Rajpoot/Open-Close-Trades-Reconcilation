import pandas as pd
import numpy as np
from pathlib import Path
import re
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class TradingReconciliation:
    """
    Reconcile and merge trading statement files from 2011-2024
    """
    
    def __init__(self):
        """Initialize the reconciliation system"""
        self.files = {}
        self.sections = {}
        self.reconciliation_report = {}
        
    def add_file(self, filepath, year=None):
        """
        Add a single file to the reconciliation
        
        Args:
            filepath: Full path to CSV file (e.g., '/content/3204_2018.csv')
            year: Optional year label (auto-detected if not provided)
        """
        if year is None:
            year = self._extract_year(filepath)
        
        self.files[year] = filepath
        print(f"Added: {year} - {filepath}")
        
        return self
    
    def add_files(self, file_dict):
        """
        Add multiple files at once
        
        Args:
            file_dict: Dictionary with year: filepath pairs
                      e.g., {'2018': '/content/3204_2018.csv', ...}
        """
        for year, filepath in file_dict.items():
            self.files[year] = filepath
            print(f"Added: {year} - {filepath}")
        
        return self
    
    def _extract_year(self, filepath):
        """Extract year from filepath"""
        match = re.search(r'(\d{4})', filepath)
        return match.group(1) if match else 'unknown'
    
    def _read_file_sections(self, filepath):
        """Parse file and extract all sections"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        sections = {
            'cash_balance': None,
            'futures': None,
            'forex': None,
            'crypto': None,
            'order_history': None,
            'trade_history': None,
            'profit_loss': None,
            'summary': None,
            'raw_content': content
        }
        
        # Split content into sections
        lines = content.split('\n')
        
        # Find section boundaries
        section_markers = {
            'Cash Balance': 'cash_balance',
            'Futures Statements': 'futures',
            'Forex Statements': 'forex',
            'Crypto': 'crypto',
            'Account Order History': 'order_history',
            'Account Trade History': 'trade_history',
            'Profits and Losses': 'profit_loss',
            'Account Summary': 'summary'
        }
        
        current_section = None
        section_start = 0
        
        for i, line in enumerate(lines):
            for marker, section_name in section_markers.items():
                if marker in line:
                    # Save previous section
                    if current_section and section_start < i:
                        section_content = '\n'.join(lines[section_start:i])
                        sections[current_section] = self._parse_section(
                            section_content, current_section
                        )
                    
                    current_section = section_name
                    section_start = i + 1
                    break
        
        # Save last section
        if current_section and section_start < len(lines):
            section_content = '\n'.join(lines[section_start:])
            sections[current_section] = self._parse_section(
                section_content, current_section
            )
        
        return sections
    
    def _parse_section(self, content, section_name):
        """Parse a specific section into DataFrame"""
        if not content.strip():
            return pd.DataFrame()
        
        try:
            # Try to parse as CSV
            from io import StringIO
            df = pd.read_csv(StringIO(content), on_bad_lines='skip')
            
            # Clean up DataFrame
            df = df.dropna(how='all')  # Remove all-null rows
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]  # Remove unnamed columns
            
            # Clean column names
            df.columns = df.columns.str.strip()
            
            return df
        except Exception as e:
            print(f"Warning: Could not parse {section_name}: {e}")
            return pd.DataFrame()
    
    def parse_all_files(self):
        """Parse all loaded files"""
        for year, filepath in sorted(self.files.items()):
            print(f"\nParsing {year} ({filepath})...")
            self.sections[year] = self._read_file_sections(filepath)
            
            # Print section info
            for section_name, df in self.sections[year].items():
                if section_name != 'raw_content' and df is not None and not df.empty:
                    print(f"  {section_name}: {len(df)} rows")
    
    def extract_cash_balances(self):
        """Extract cash balance data from all years"""
        all_balances = []
        
        for year, sections in self.sections.items():
            df = sections.get('cash_balance')
            if df is not None and not df.empty:
                df = df.copy()
                df['year'] = year
                all_balances.append(df)
        
        if all_balances:
            combined = pd.concat(all_balances, ignore_index=True)
            
            # Clean and parse amounts
            if 'BALANCE' in combined.columns:
                combined['BALANCE'] = combined['BALANCE'].apply(self._parse_amount)
            if 'AMOUNT' in combined.columns:
                combined['AMOUNT'] = combined['AMOUNT'].apply(self._parse_amount)
            
            # Parse dates
            if 'DATE' in combined.columns:
                combined['DATE'] = pd.to_datetime(combined['DATE'], errors='coerce')
            
            return combined.sort_values('DATE') if 'DATE' in combined.columns else combined
        
        return pd.DataFrame()
    
    def extract_trades(self):
        """Extract all trade history"""
        all_trades = []
        
        for year, sections in self.sections.items():
            df = sections.get('trade_history')
            if df is not None and not df.empty:
                df = df.copy()
                df['year'] = year
                all_trades.append(df)
        
        if all_trades:
            combined = pd.concat(all_trades, ignore_index=True)
            
            # Parse price columns
            price_cols = ['Price', 'Net Price']
            for col in price_cols:
                if col in combined.columns:
                    combined[col] = combined[col].apply(self._parse_amount)
            
            return combined
        
        return pd.DataFrame()
    
    def extract_profit_loss(self):
        """Extract P&L data"""
        all_pl = []
        
        for year, sections in self.sections.items():
            df = sections.get('profit_loss')
            if df is not None and not df.empty:
                df = df.copy()
                df['year'] = year
                all_pl.append(df)
        
        if all_pl:
            combined = pd.concat(all_pl, ignore_index=True)
            
            # Parse P&L columns
            pl_cols = ['P/L Open', 'P/L Day', 'P/L YTD', 'P/L Diff']
            for col in pl_cols:
                if col in combined.columns:
                    combined[col] = combined[col].apply(self._parse_amount)
            
            return combined
        
        return pd.DataFrame()
    
    def _parse_amount(self, value):
        """Parse dollar amount from string"""
        if pd.isna(value):
            return 0.0
        
        if isinstance(value, (int, float)):
            return float(value)
        
        # Remove $, commas, quotes, spaces, and parentheses
        cleaned = str(value).replace('$', '').replace(',', '').replace('"', '')
        cleaned = cleaned.replace(' ', '').strip()
        
        # Handle parentheses (negative values)
        if '(' in cleaned and ')' in cleaned:
            cleaned = '-' + cleaned.replace('(', '').replace(')', '')
        
        try:
            return float(cleaned)
        except (ValueError, AttributeError):
            return 0.0
    
    def reconcile_balances(self):
        """Reconcile year-over-year balances"""
        balances = self.extract_cash_balances()
        
        if balances.empty:
            print("No balance data found")
            return pd.DataFrame()
        
        # Get start and end balance for each year
        yearly_balances = []
        
        for year in sorted(self.sections.keys()):
            year_data = balances[balances['year'] == year]
            
            if not year_data.empty and 'BALANCE' in year_data.columns:
                start_balance = year_data['BALANCE'].iloc[0]
                end_balance = year_data['BALANCE'].iloc[-1]
                
                yearly_balances.append({
                    'year': year,
                    'start_balance': start_balance,
                    'end_balance': end_balance,
                    'net_change': end_balance - start_balance
                })
        
        df_yearly = pd.DataFrame(yearly_balances)
        
        # Check for gaps
        df_yearly['prev_year_end'] = df_yearly['end_balance'].shift(1)
        df_yearly['balance_gap'] = df_yearly['start_balance'] - df_yearly['prev_year_end']
        df_yearly['has_gap'] = df_yearly['balance_gap'].abs() > 0.01
        
        return df_yearly
    
    def generate_reconciliation_report(self):
        """Generate comprehensive reconciliation report"""
        print("\n" + "="*80)
        print("TRADING ACCOUNT RECONCILIATION REPORT")
        print("="*80)
        
        # Year coverage
        years = sorted(self.sections.keys())
        print(f"\nYears Covered: {years[0]} - {years[-1]}")
        print(f"Total Years: {len(years)}")
        
        # Balance reconciliation
        print("\n" + "-"*80)
        print("YEAR-OVER-YEAR BALANCE RECONCILIATION")
        print("-"*80)
        
        balance_recon = self.reconcile_balances()
        
        if not balance_recon.empty:
            pd.set_option('display.float_format', lambda x: f'${x:,.2f}')
            print("\n", balance_recon.to_string(index=False))
            
            # Gaps
            gaps = balance_recon[balance_recon['has_gap'] == True]
            if not gaps.empty:
                print("\n⚠️  RECONCILIATION GAPS FOUND:")
                print(gaps[['year', 'start_balance', 'prev_year_end', 'balance_gap']].to_string(index=False))
            else:
                print("\n✓ No reconciliation gaps found")
        
        # Trade statistics
        print("\n" + "-"*80)
        print("TRADE STATISTICS")
        print("-"*80)
        
        trades = self.extract_trades()
        if not trades.empty:
            print(f"\nTotal Trades: {len(trades):,}")
            print(f"\nTrades by Year:")
            year_counts = trades['year'].value_counts().sort_index()
            for year, count in year_counts.items():
                print(f"  {year}: {count:,}")
        
        # P&L Summary
        print("\n" + "-"*80)
        print("PROFIT & LOSS SUMMARY")
        print("-"*80)
        
        pl_data = self.extract_profit_loss()
        if not pl_data.empty and 'P/L YTD' in pl_data.columns:
            yearly_pl = pl_data.groupby('year')['P/L YTD'].sum()
            print("\nP&L by Year:")
            for year, pl in yearly_pl.items():
                print(f"  {year}: ${pl:,.2f}")
            
            print(f"\nTotal Cumulative P&L: ${yearly_pl.sum():,.2f}")
        
        self.reconciliation_report = {
            'balance_reconciliation': balance_recon,
            'trades': trades,
            'profit_loss': pl_data
        }
        
        return self.reconciliation_report
    
    def export_consolidated_data(self, output_dir='./output'):
        """Export consolidated data to CSV files"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"\nExporting consolidated data to {output_path}...")
        
        # Export cash balances
        balances = self.extract_cash_balances()
        if not balances.empty:
            filepath = output_path / 'consolidated_cash_balances_2010-2024.csv'
            balances.to_csv(filepath, index=False)
            print(f"✓ Exported: {filepath} ({len(balances)} rows)")
        
        # Export trades
        trades = self.extract_trades()
        if not trades.empty:
            filepath = output_path / 'consolidated_trades_2010-2024.csv'
            trades.to_csv(filepath, index=False)
            print(f"✓ Exported: {filepath} ({len(trades)} rows)")
        
        # Export P&L
        pl = self.extract_profit_loss()
        if not pl.empty:
            filepath = output_path / 'consolidated_profit_loss_2010-2024.csv'
            pl.to_csv(filepath, index=False)
            print(f"✓ Exported: {filepath} ({len(pl)} rows)")
        
        # Export reconciliation report
        if self.reconciliation_report:
            balance_recon = self.reconciliation_report.get('balance_reconciliation')
            if balance_recon is not None and not balance_recon.empty:
                filepath = output_path / 'reconciliation_report.csv'
                balance_recon.to_csv(filepath, index=False)
                print(f"✓ Exported: {filepath}")
        
        print("\n✓ Export complete!")


# ==============================================================================
# USAGE EXAMPLE - Direct File Paths
# ==============================================================================

if __name__ == "__main__":
    # Initialize reconciliation
    reconciler = TradingReconciliation()
    
    # METHOD 1: Add files one by one
    reconciler.add_file('/content/3204_2010.csv', '2010')
    reconciler.add_file('/content/3204_2011.csv', '2011')
    reconciler.add_file('/content/3204_2012.csv', '2012')
    reconciler.add_file('/content/3204_2013.csv', '2013')
    reconciler.add_file('/content/3204_2014.csv', '2014')
    reconciler.add_file('/content/3204_2015.csv', '2015')
    reconciler.add_file('/content/3204_2016.csv', '2016')
    reconciler.add_file('/content/3204_2017.csv', '2017')
    reconciler.add_file('/content/3204_2018.csv', '2018')
    reconciler.add_file('/content/3204_2019.csv', '2019')
    reconciler.add_file('/content/3204_2020.csv', '2020')
    reconciler.add_file('/content/3204_2021.csv', '2021')
    reconciler.add_file('/content/3204_2022.csv', '2022')
    reconciler.add_file('/content/3204_2023.csv', '2023')
    reconciler.add_file('/content/3204_2024.csv', '2024')
    
    # METHOD 2: Or add all at once using dictionary
    """
    files = {
        '2010': '/content/3204_2010.csv',
        '2011': '/content/3204_2011.csv',
        '2012': '/content/3204_2012.csv',
        '2013': '/content/3204_2013.csv',
        '2014': '/content/3204_2014.csv',
        '2015': '/content/3204_2015.csv',
        '2016': '/content/3204_2016.csv',
        '2017': '/content/3204_2017.csv',
        '2018': '/content/3204_2018.csv',
        '2019': '/content/3204_2019.csv',
        '2020': '/content/3204_2020.csv',
        '2021': '/content/3204_2021.csv',
        '2022': '/content/3204_2022.csv',
        '2023': '/content/3204_2023.csv',
        '2024': '/content/3204_2024.csv',
    }
    reconciler.add_files(files)
    """
    
    # Parse all files
    reconciler.parse_all_files()
    
    # Generate reconciliation report
    report = reconciler.generate_reconciliation_report()
    
    # Export consolidated data
    reconciler.export_consolidated_data(output_dir='/content/consolidated_output')
    
    # Access specific data
    print("\n" + "="*80)
    print("ACCESSING CONSOLIDATED DATA")
    print("="*80)
    
    # Get all cash balances
    all_balances = reconciler.extract_cash_balances()
    print(f"\nTotal balance records: {len(all_balances)}")
    
    # Get all trades
    all_trades = reconciler.extract_trades()
    print(f"Total trade records: {len(all_trades)}")
    
    # Get P&L data
    all_pl = reconciler.extract_profit_loss()
    print(f"Total P&L records: {len(all_pl)}")
    
    # Example: Filter trades by symbol
    if not all_trades.empty and 'Symbol' in all_trades.columns:
        print("\n\nTop 10 Most Traded Symbols:")
        top_symbols = all_trades['Symbol'].value_counts().head(10)
        print(top_symbols)
    
    # Example: Monthly balance progression
    if not all_balances.empty and 'DATE' in all_balances.columns:
        print("\n\nAccount Balance Over Time (Last 12 Months):")
        all_balances['year_month'] = all_balances['DATE'].dt.to_period('M')
        monthly_end_balance = all_balances.groupby('year_month')['BALANCE'].last()
        print(monthly_end_balance.tail(12))


def analyze_trading_performance(reconciler):
    """Advanced performance analysis"""
    trades = reconciler.extract_trades()
    
    if trades.empty:
        return
    
    print("\n" + "="*80)
    print("TRADING PERFORMANCE ANALYSIS")
    print("="*80)
    
    # Win rate by symbol (if we have price data)
    if 'Symbol' in trades.columns and 'Net Price' in trades.columns:
        symbol_analysis = trades.groupby('Symbol').agg({
            'Net Price': ['count', 'sum', 'mean']
        }).round(2)
        symbol_analysis.columns = ['Trade Count', 'Total P&L', 'Avg P&L']
        
        print("\nPerformance by Symbol:")
        print(symbol_analysis.sort_values('Total P&L', ascending=False).head(10))

def find_largest_trades(reconciler, top_n=20):
    """Find largest trades by value"""
    balances = reconciler.extract_cash_balances()
    
    if balances.empty or 'AMOUNT' not in balances.columns:
        return
    
    balances['abs_amount'] = balances['AMOUNT'].abs()
    largest = balances.nlargest(top_n, 'abs_amount')[
        ['DATE', 'TYPE', 'DESCRIPTION', 'AMOUNT', 'BALANCE']
    ]
    
    print("\n" + "="*80)
    print(f"TOP {top_n} LARGEST TRANSACTIONS")
    print("="*80)
    print(largest.to_string(index=False))

def calculate_drawdowns(reconciler):
    """Calculate maximum drawdown periods"""
    balances = reconciler.extract_cash_balances()
    
    if balances.empty or 'BALANCE' not in balances.columns:
        return
    
    balances = balances.sort_values('DATE')
    balances['cummax'] = balances['BALANCE'].cummax()
    balances['drawdown'] = balances['BALANCE'] - balances['cummax']
    balances['drawdown_pct'] = (balances['drawdown'] / balances['cummax'] * 100)
    
    max_drawdown_idx = balances['drawdown'].idxmin()
    max_drawdown = balances.loc[max_drawdown_idx]
    
    print("\n" + "="*80)
    print("DRAWDOWN ANALYSIS")
    print("="*80)
    print(f"\nMaximum Drawdown: ${max_drawdown['drawdown']:,.2f} ({max_drawdown['drawdown_pct']:.2f}%)")
    print(f"Date: {max_drawdown['DATE']}")
    print(f"Balance at Drawdown: ${max_drawdown['BALANCE']:,.2f}")
    print(f"Peak Balance: ${max_drawdown['cummax']:,.2f}")



