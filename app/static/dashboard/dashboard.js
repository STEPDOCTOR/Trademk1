// Dashboard JavaScript
const API_BASE = '/api/v1';
let charts = {};
let updateInterval;

// Utility functions
function formatMoney(value) {
    const formatted = new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(Math.abs(value));
    
    if (value > 0) {
        return `<span class="profit">+${formatted}</span>`;
    } else if (value < 0) {
        return `<span class="loss">-${formatted.substring(1)}</span>`;
    }
    return formatted;
}

function formatPercent(value) {
    const formatted = `${Math.abs(value).toFixed(2)}%`;
    if (value > 0) {
        return `<span class="profit">+${formatted}</span>`;
    } else if (value < 0) {
        return `<span class="loss">-${formatted}</span>`;
    }
    return formatted;
}

function formatTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
}

// Update functions
async function updateMetrics() {
    try {
        // Get realtime metrics
        const response = await axios.get(`${API_BASE}/performance/realtime`);
        const data = response.data;
        
        // Update P&L metrics
        document.getElementById('totalPnL').innerHTML = formatMoney(data.total_pnl || 0);
        document.getElementById('totalPnLPct').innerHTML = formatPercent(data.total_pnl_pct || 0);
        document.getElementById('todayPnL').innerHTML = formatMoney(data.realized_pnl || 0);
        
        // Update win rate
        if (data.trades_today > 0) {
            const winRate = (data.winning_trades_today / data.trades_today * 100);
            document.getElementById('winRate').innerHTML = `${winRate.toFixed(1)}%`;
            document.getElementById('winLoss').innerHTML = 
                `${data.winning_trades_today}W / ${data.losing_trades_today}L`;
        }
        
        // Update positions
        document.getElementById('openPositions').innerHTML = data.open_positions || 0;
        document.getElementById('positionValue').innerHTML = 
            `Value: ${formatMoney(data.total_position_value || 0)}`;
        
        // Update daily limits
        if (data.limit_status) {
            updateLimitBars(data.limit_status);
            checkAlerts(data.limit_status);
        }
        
    } catch (error) {
        console.error('Error updating metrics:', error);
    }
}

function updateLimitBars(limitStatus) {
    const currentPnL = limitStatus.current_pnl || 0;
    const lossLimit = Math.abs(limitStatus.loss_limit || 1000);
    const profitTarget = limitStatus.profit_target || 2000;
    
    if (currentPnL < 0) {
        // Show loss progress
        const lossPct = Math.min(100, Math.abs(currentPnL) / lossLimit * 100);
        document.getElementById('lossLimitBar').style.width = `${lossPct}%`;
        document.getElementById('lossLimitText').textContent = 
            `$${Math.abs(currentPnL).toFixed(0)} / $${lossLimit}`;
        
        // Reset profit bar
        document.getElementById('profitTargetBar').style.width = '0%';
        document.getElementById('profitTargetText').textContent = `$0 / $${profitTarget}`;
    } else {
        // Show profit progress
        const profitPct = Math.min(100, currentPnL / profitTarget * 100);
        document.getElementById('profitTargetBar').style.width = `${profitPct}%`;
        document.getElementById('profitTargetText').textContent = 
            `$${currentPnL.toFixed(0)} / $${profitTarget}`;
        
        // Reset loss bar
        document.getElementById('lossLimitBar').style.width = '0%';
        document.getElementById('lossLimitText').textContent = `$0 / $${lossLimit}`;
    }
}

function checkAlerts(limitStatus) {
    const alertBanner = document.getElementById('alertBanner');
    const alertIcon = document.getElementById('alertIcon');
    const alertTitle = document.getElementById('alertTitle');
    const alertMessage = document.getElementById('alertMessage');
    
    if (limitStatus.loss_limit_hit) {
        alertBanner.className = 'mb-6 p-4 rounded-lg shadow-md bg-red-100 border border-red-400';
        alertIcon.className = 'fas fa-exclamation-circle text-2xl mr-3 text-red-600';
        alertTitle.textContent = 'Daily Loss Limit Hit!';
        alertMessage.textContent = `Trading stopped. Loss: ${formatMoney(limitStatus.current_pnl)}`;
        alertBanner.classList.remove('hidden');
    } else if (limitStatus.pct_to_loss_limit > 80) {
        alertBanner.className = 'mb-6 p-4 rounded-lg shadow-md bg-yellow-100 border border-yellow-400';
        alertIcon.className = 'fas fa-exclamation-triangle text-2xl mr-3 text-yellow-600';
        alertTitle.textContent = 'Approaching Loss Limit';
        alertMessage.textContent = `${limitStatus.pct_to_loss_limit.toFixed(0)}% of daily loss limit`;
        alertBanner.classList.remove('hidden');
    } else if (limitStatus.profit_target_hit) {
        alertBanner.className = 'mb-6 p-4 rounded-lg shadow-md bg-green-100 border border-green-400';
        alertIcon.className = 'fas fa-check-circle text-2xl mr-3 text-green-600';
        alertTitle.textContent = 'Profit Target Reached!';
        alertMessage.textContent = `Congratulations! Profit: ${formatMoney(limitStatus.current_pnl)}`;
        alertBanner.classList.remove('hidden');
    } else {
        alertBanner.classList.add('hidden');
    }
}

async function updateBotStatus() {
    try {
        const response = await axios.get(`${API_BASE}/autonomous/status`);
        const status = response.data;
        
        const statusElement = document.getElementById('botStatus');
        if (status.running) {
            statusElement.innerHTML = 
                '<i class="fas fa-circle text-green-400"></i> Running';
            statusElement.className = 'px-3 py-1 rounded-full text-sm bg-green-900';
        } else {
            statusElement.innerHTML = 
                '<i class="fas fa-circle text-red-400"></i> Stopped';
            statusElement.className = 'px-3 py-1 rounded-full text-sm bg-red-900';
        }
    } catch (error) {
        console.error('Error updating bot status:', error);
    }
}

async function updateTrades() {
    try {
        const response = await axios.get(`${API_BASE}/performance/trades/recent?limit=10`);
        const trades = response.data;
        
        const tbody = document.getElementById('tradesTable');
        if (trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-gray-400">No recent trades</td></tr>';
            return;
        }
        
        tbody.innerHTML = trades.map(trade => `
            <tr class="border-b hover:bg-gray-50">
                <td class="py-2">${formatTime(trade.executed_at)}</td>
                <td class="py-2 font-medium">${trade.symbol}</td>
                <td class="py-2">
                    <span class="px-2 py-1 text-xs rounded-full ${
                        trade.type === 'buy' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }">
                        ${trade.type.toUpperCase()}
                    </span>
                </td>
                <td class="py-2 text-right">
                    ${trade.profit_loss ? formatMoney(trade.profit_loss) : '--'}
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error updating trades:', error);
    }
}

async function updatePositions() {
    try {
        const response = await axios.get(`${API_BASE}/trading/positions`);
        const positions = response.data.positions || [];
        
        const tbody = document.getElementById('positionsTable');
        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-gray-400">No open positions</td></tr>';
            return;
        }
        
        tbody.innerHTML = positions.map(position => `
            <tr class="border-b hover:bg-gray-50">
                <td class="py-2 font-medium">${position.symbol}</td>
                <td class="py-2">${position.qty}</td>
                <td class="py-2">$${position.avg_price.toFixed(2)}</td>
                <td class="py-2 text-right">
                    ${formatMoney(position.unrealized_pnl || 0)}
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error updating positions:', error);
    }
}

async function updateCharts() {
    try {
        // Get daily performance data
        const response = await axios.get(`${API_BASE}/performance/daily?days=7`);
        const dailyData = response.data;
        
        // Update P&L chart
        updatePnLChart(dailyData);
        
        // Get summary for trade distribution
        const summaryResponse = await axios.get(`${API_BASE}/performance/summary?days=30`);
        const summary = summaryResponse.data;
        updateTradeChart(summary);
        
    } catch (error) {
        console.error('Error updating charts:', error);
    }
}

function updatePnLChart(dailyData) {
    const ctx = document.getElementById('pnlChart').getContext('2d');
    
    const labels = dailyData.map(d => new Date(d.date).toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric' 
    }));
    const pnlData = dailyData.map(d => d.total_pnl);
    
    if (charts.pnl) {
        charts.pnl.data.labels = labels;
        charts.pnl.data.datasets[0].data = pnlData;
        charts.pnl.update();
    } else {
        charts.pnl = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily P&L',
                    data: pnlData,
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }
}

function updateTradeChart(summary) {
    const ctx = document.getElementById('tradeChart').getContext('2d');
    
    if (!summary.trades_by_strategy) return;
    
    const labels = Object.keys(summary.trades_by_strategy);
    const data = Object.values(summary.trades_by_strategy);
    
    if (charts.trades) {
        charts.trades.data.labels = labels;
        charts.trades.data.datasets[0].data = data;
        charts.trades.update();
    } else {
        charts.trades = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels.map(l => l.charAt(0).toUpperCase() + l.slice(1)),
                datasets: [{
                    data: data,
                    backgroundColor: [
                        'rgba(59, 130, 246, 0.8)',
                        'rgba(239, 68, 68, 0.8)',
                        'rgba(16, 185, 129, 0.8)',
                        'rgba(245, 158, 11, 0.8)',
                        'rgba(139, 92, 246, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
}

function updateClock() {
    const now = new Date();
    document.getElementById('currentTime').textContent = 
        now.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        });
    
    // Update market status
    const hour = now.getUTCHours();
    const day = now.getUTCDay();
    const isWeekend = day === 0 || day === 6;
    const isMarketHours = hour >= 14 && hour < 21; // 9:30 AM - 4 PM EST
    
    const marketStatus = document.getElementById('marketStatus');
    if (isWeekend) {
        marketStatus.textContent = 'Market: Closed (Weekend)';
        marketStatus.className = 'text-sm text-red-400';
    } else if (isMarketHours) {
        marketStatus.textContent = 'Market: Open';
        marketStatus.className = 'text-sm text-green-400';
    } else {
        marketStatus.textContent = 'Market: Closed';
        marketStatus.className = 'text-sm text-red-400';
    }
}

function dismissAlert() {
    document.getElementById('alertBanner').classList.add('hidden');
}

// Initialize dashboard
async function init() {
    // Initial updates
    updateClock();
    await updateBotStatus();
    await updateMetrics();
    await updateTrades();
    await updatePositions();
    await updateCharts();
    
    // Set up intervals
    setInterval(updateClock, 1000);
    setInterval(updateMetrics, 5000); // Every 5 seconds
    setInterval(updateBotStatus, 10000); // Every 10 seconds
    setInterval(updateTrades, 15000); // Every 15 seconds
    setInterval(updatePositions, 15000); // Every 15 seconds
    setInterval(updateCharts, 60000); // Every minute
}

// Start when page loads
document.addEventListener('DOMContentLoaded', init);