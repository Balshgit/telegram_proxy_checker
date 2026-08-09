import './WelcomePage.css'

function WelcomePage() {
  return (
    <div className="welcome-container">
      <div className="welcome-card">
        <div className="welcome-icon">🔍</div>
        <h1>Telegram Proxy Checker</h1>
        <p className="welcome-subtitle">
          Инструмент для проверки и мониторинга Telegram-прокси
        </p>
        <div className="welcome-features">
          <div className="feature-item">
            <span className="feature-icon">⚡</span>
            <span>Быстрая проверка прокси</span>
          </div>
          <div className="feature-item">
            <span className="feature-icon">📊</span>
            <span>Статистика и аналитика</span>
          </div>
          <div className="feature-item">
            <span className="feature-icon">🔄</span>
            <span>Автоматический мониторинг</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default WelcomePage
