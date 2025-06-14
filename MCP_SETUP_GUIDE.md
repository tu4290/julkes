# Elite Options System - MCP Database Setup Guide

## Overview
This guide will help you complete the setup of the Database MCP (Model Context Protocol) server to connect your Elite Options System with Claude Desktop for direct database access.

## Current Status ✅
- [x] MCP Database Server built and ready
- [x] SQLite database created (`data/elite_options.db`)
- [x] Database schema initialized with 6 tables:
  - `options_chains` - Options market data
  - `portfolio_positions` - Your trading positions
  - `market_data` - Stock market data cache
  - `performance_metrics` - Historical performance tracking
  - `trading_signals` - Trading alerts and signals
  - `risk_metrics` - Portfolio risk analysis
- [x] Configuration file created (`claude_desktop_config.json`)

## Next Steps

### 1. Copy Configuration to Claude Desktop

You need to copy the MCP configuration to Claude Desktop's config file location:

**Windows Location:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Steps:**
1. Open File Explorer
2. Type `%APPDATA%\Claude` in the address bar
3. If the folder doesn't exist, create it
4. Copy the contents from your project's `claude_desktop_config.json` to this location

### 2. Restart Claude Desktop

After copying the configuration:
1. Close Claude Desktop completely
2. Restart Claude Desktop
3. The MCP server should automatically connect

### 3. Verify Connection

Once Claude Desktop restarts, you should be able to:
- Ask Claude to query your options database
- Request portfolio analysis
- Get market data insights
- Analyze trading performance

## Example Queries You Can Try

Once connected, you can ask Claude:

```
"Show me all the tables in my options database"
"What's the current portfolio value?"
"Analyze my trading performance metrics"
"Show me recent options chains data"
"What are my open positions?"
```

## Database Schema Details

### Options Chains Table
- Stores real-time and historical options data
- Includes Greeks (delta, gamma, theta, vega, rho)
- Tracks bid/ask spreads and volume

### Portfolio Positions Table
- Tracks all your trading positions
- Calculates P&L (realized and unrealized)
- Supports both options and stock positions

### Performance Metrics Table
- Daily portfolio performance tracking
- Key metrics: Sharpe ratio, max drawdown, win rate
- Historical performance analysis

### Market Data Table
- Cached market data for quick access
- Fundamental data (P/E, beta, market cap)
- 52-week highs/lows

### Trading Signals Table
- Custom trading alerts and signals
- Target prices and stop losses
- Signal strength scoring

### Risk Metrics Table
- Portfolio-level risk analysis
- VaR (Value at Risk) calculations
- Greek exposures and concentration risk

## Configuration File Content

Your `claude_desktop_config.json` should contain:

```json
{
  "mcpServers": {
    "elite-options-database": {
      "command": "node",
      "args": [
        "c:\\Users\\dangt\\OneDrive\\Desktop\\elite_options_system_v2_5(julkess)\\mcp-database-server\\dist\\src\\index.js",
        "c:\\Users\\dangt\\OneDrive\\Desktop\\elite_options_system_v2_5(julkess)\\data\\elite_options.db"
      ],
      "env": {
        "NODE_ENV": "development"
      }
    }
  }
}
```

## Troubleshooting

### MCP Server Not Connecting
1. Verify Node.js is installed and accessible
2. Check that the database file path is correct
3. Ensure Claude Desktop has permission to access the files
4. Check Claude Desktop logs for error messages

### Database Access Issues
1. Verify the SQLite database file exists
2. Check file permissions
3. Ensure the database schema was properly initialized

### Path Issues
1. Use absolute paths in the configuration
2. Escape backslashes in JSON (use `\\` instead of `\`)
3. Verify all file paths exist

## Sample Data

The database has been initialized with sample data:
- 5 market data entries (SPY, QQQ, AAPL, MSFT, GOOGL)
- 3 performance metric entries
- All tables are ready for your real trading data

## Next Development Steps

1. **Data Integration**: Connect your trading platform APIs to populate real data
2. **Real-time Updates**: Set up automated data feeds
3. **Advanced Analytics**: Implement custom trading strategies
4. **Risk Management**: Set up automated risk monitoring
5. **Reporting**: Create automated performance reports

## Security Notes

- The database is currently set up for local development
- Consider implementing backup strategies for your trading data
- For production use, consider additional security measures
- Keep your configuration files secure and don't share them publicly

---

**Ready to use!** Once you complete the Claude Desktop configuration, you'll have direct database access through Claude for powerful options trading analysis.