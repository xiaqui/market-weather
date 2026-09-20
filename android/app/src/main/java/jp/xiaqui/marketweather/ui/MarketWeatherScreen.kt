package jp.xiaqui.marketweather.ui
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import jp.xiaqui.marketweather.model.Forecast
import jp.xiaqui.marketweather.model.Market
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
private val colors = lightColorScheme(primary = Color(0xFF176B55), background = Color(0xFFF4F8F6), surface = Color.White)
@Composable fun MarketWeatherTheme(content: @Composable () -> Unit) = MaterialTheme(colorScheme = colors, content = content)
@Composable
fun MarketWeatherScreen(forecast: Forecast) {
    var selected by remember { mutableStateOf<Market?>(null) }
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Text("MARKET WEATHER", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.primary)
            Text("本日の金融天気予報", style = MaterialTheme.typography.titleMedium)
            Text("生成日時 ${formatDate(forecast.generatedAt)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
        }
        items(forecast.markets, key = { it.id }) { market -> MarketWeatherCard(market) { selected = market } }
    }
    selected?.let { market ->
        AlertDialog(onDismissRequest = { selected = null }, confirmButton = { TextButton(onClick = { selected = null }) { Text("閉じる") } }, title = { Text("${market.name} の詳細") }, text = {
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text("現在値: ${formattedNumber(market.current)}")
                Text("天気: ${weatherLabel(market.weather)}")
                Text("上昇確率: ${(market.upProbability * 100).toInt()}%")
                Text("予想レンジ: ${formattedNumber(market.rangeLow)} ～ ${formattedNumber(market.rangeHigh)}")
                Text("信頼度: ${(market.confidence * 100).toInt()}%")
                Text("リスク状態: ${riskLabel(market.risk)}")
            }
        })
    }
}
private fun formatDate(value: String): String = runCatching { OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("yyyy/MM/dd HH:mm")) }.getOrDefault(value)
