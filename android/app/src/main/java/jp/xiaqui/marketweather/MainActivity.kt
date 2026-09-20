package jp.xiaqui.marketweather
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import jp.xiaqui.marketweather.data.ForecastRepository
import jp.xiaqui.marketweather.ui.MarketWeatherScreen
import jp.xiaqui.marketweather.ui.MarketWeatherTheme
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val forecast = ForecastRepository().load(this)
        setContent { MarketWeatherTheme { MarketWeatherScreen(forecast) } }
    }
}
