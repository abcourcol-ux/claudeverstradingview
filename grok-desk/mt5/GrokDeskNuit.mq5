//+------------------------------------------------------------------+
//| GrokDeskNuit.mq5 — règle de nuit Grok Desk (XAUUSD, M5)          |
//| Reproduit grok-desk/backtests/month.py --window nuit --pips 50   |
//|   --k 0 --maxsl 1 :                                              |
//|   - fenêtre 00h30–04h Paris ; signal sur bougie M5 clôturée      |
//|     entre 00h45 et 03h10 (heure d'ouverture de la bougie)        |
//|   - amplitude (vrai range) >= 2 × ATR14 (Wilder, valeur d'avant) |
//|   - clôture du bon côté du VWAP de séance (moyenne simple hlc3)  |
//|     et bougie dans le même sens ; refus si > 3 ATR du VWAP       |
//|   - entrée au marché à l'ouverture de la bougie suivante         |
//|   - SL 5 $ (50 pips) ; TP 1R / 2R / 3R par tiers ; BE après TP1  |
//|     (niveaux calculés depuis la clôture de la bougie signal)     |
//|   - 1 position à la fois, 5 trades max, arrêt après 1 SL         |
//|   - tout est fermé à 03h55 Paris                                 |
//| Aucune IA : l'EA applique toujours la même règle.                |
//+------------------------------------------------------------------+
#property copyright "Grok Desk"
#property version   "1.00"
#property description "Règle de nuit XAUUSD 00h30-04h Paris · SL 50 pips · TP 1R/2R/3R par tiers · BE après TP1 · arrêt après 1 SL"
#include <Trade/Trade.mqh>

enum ENUM_GD_SIZING { GD_RISK_PCT = 0,   // Risque en % de l'equity
                      GD_FIXED_LOT = 1 }; // Lot fixe
enum ENUM_GD_SRVTZ  { GD_NY_PLUS_7 = 0,  // Heure serveur = New York + 7 h (Axi et la plupart des brokers MT5)
                      GD_MANUAL = 1 };    // Décalage manuel fixe

input group "💰 Taille"
input ENUM_GD_SIZING InpSizing   = GD_RISK_PCT; // Mode de calcul du lot
input double InpRiskPct          = 0.5;   // Risque par trade (% de l'equity)
input double InpFixedLot         = 0.03;  // Lot fixe (si mode lot fixe)
input group "🎯 Règle"
input double InpSlUsd            = 5.0;   // SL en $ par once (5 $ = 50 pips)
input double InpRangeAtr         = 2.0;   // Amplitude minimum (× ATR)
input double InpMaxExtAtr        = 3.0;   // Refus si clôture > N × ATR du VWAP
input int    InpAtrLen           = 14;    // Période ATR
input int    InpMaxTrades        = 5;     // Trades max par nuit
input int    InpMaxSL            = 1;     // Arrêt de la nuit après N SL (0 = désactivé)
input bool   InpAllowShort       = true;  // Autoriser les ventes
input group "🕐 Horaires (heure de Paris)"
input int    InpWinStartMin      = 30;    // Début de fenêtre (minutes après minuit, 30 = 00h30)
input int    InpWinEndMin        = 240;   // Fin de fenêtre (240 = 04h00)
input int    InpNoFirstMin       = 15;    // Pas de signal les N premières minutes
input int    InpNoLastMin        = 45;    // Pas de signal les N dernières minutes
input int    InpFlattenMin       = 5;     // Tout fermer N minutes avant la fin
input ENUM_GD_SRVTZ InpServerTz  = GD_NY_PLUS_7; // Fuseau du serveur du broker
input int    InpServerUtcOffsetH = 2;     // Décalage serveur/UTC en heures (si manuel)
input group "🛡️ Protection du compte (prop firm)"
input double InpEquityFloor      = 0;     // Plancher d'equity (ex. 170000 ; 0 = désactivé)
input double InpHalfRiskDD       = 0;     // Risque ÷ 2 si equity < plus haut − X $ (ex. 5000 ; 0 = désactivé)
input group "⚙️ Divers"
input long   InpMagic            = 20261124; // Numéro magique
input bool   InpPush             = true;  // Notifications sur l'app MT5 mobile

CTrade   trade;
datetime g_lastBar = 0;
ulong    g_cacheTicket = 0;
double   g_cacheInitVol = 0;

//--- dates / fuseaux --------------------------------------------------
datetime MakeDate(int y, int m, int d, int h)
{
   MqlDateTime s; ZeroMemory(s);
   s.year = y; s.mon = m; s.day = d; s.hour = h;
   return StructToTime(s);
}
int Dow(datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.day_of_week; }
int YearOf(datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.year; }
datetime NthSunday(int y, int m, int n, int h)   // n-ième dimanche du mois, à h heures UTC
{
   datetime t = MakeDate(y, m, 1, h);
   while(Dow(t) != 0) t += 86400;
   return t + (n - 1) * 7 * 86400;
}
datetime LastSunday(int y, int m, int h)         // dernier dimanche (mars / octobre : 31 jours)
{
   datetime t = MakeDate(y, m, 31, h);
   while(Dow(t) != 0) t -= 86400;
   return t;
}
int ParisOffsetH(datetime utc)   // heure d'été : dernier dimanche de mars 01:00 UTC → dernier dimanche d'octobre 01:00 UTC
{
   int y = YearOf(utc);
   return (utc >= LastSunday(y, 3, 1) && utc < LastSunday(y, 10, 1)) ? 2 : 1;
}
int NyOffsetH(datetime utc)      // heure d'été US : 2e dimanche de mars 07:00 UTC → 1er dimanche de novembre 06:00 UTC
{
   int y = YearOf(utc);
   return (utc >= NthSunday(y, 3, 2, 7) && utc < NthSunday(y, 11, 1, 6)) ? -4 : -5;
}
datetime ServerToUtc(datetime srv)
{
   if(InpServerTz == GD_MANUAL) return srv - InpServerUtcOffsetH * 3600;
   int off = NyOffsetH(srv - 3 * 3600) + 7;      // serveur = New York + 7 h
   return srv - off * 3600;
}
int ParisMinutes(datetime srv)   // minutes après minuit, heure de Paris
{
   datetime utc = ServerToUtc(srv);
   MqlDateTime s; TimeToStruct(utc + ParisOffsetH(utc) * 3600, s);
   return s.hour * 60 + s.min;
}

//--- outils -----------------------------------------------------------
double LossPerLot(double dist)
{
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tv <= 0) tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   return ts > 0 ? dist / ts * tv : 0;
}
double FloorLot(double v)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   return step > 0 ? MathFloor(v / step + 1e-9) * step : v;
}
void Notify(string msg)
{
   Print(msg);
   if(InpPush && TerminalInfoInteger(TERMINAL_NOTIFICATIONS_ENABLED)) SendNotification(msg);
}
bool OurPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
      { ticket = t; return true; }
   }
   return false;
}
double InitialVolume(ulong ticket, long posId)
{
   if(ticket == g_cacheTicket && g_cacheInitVol > 0) return g_cacheInitVol;
   double v = 0;
   if(HistorySelectByPosition(posId))
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong d = HistoryDealGetTicket(i);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) v += HistoryDealGetDouble(d, DEAL_VOLUME);
      }
   if(v <= 0) v = PositionGetDouble(POSITION_VOLUME);
   g_cacheTicket = ticket; g_cacheInitVol = v;
   return v;
}

//--- compteurs de la nuit (relus dans l'historique : robustes à un redémarrage)
void NightCounters(datetime sessStart, int &nTrades, int &nSL, datetime &lastDeal)
{
   nTrades = 0; nSL = 0; lastDeal = 0;
   if(!HistorySelect(sessStart, TimeCurrent() + 3600)) return;
   long   ids[]; double vin[]; double pnl[];
   int n = 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol || HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic) continue;
      long id = HistoryDealGetInteger(d, DEAL_POSITION_ID);
      datetime dt = (datetime)HistoryDealGetInteger(d, DEAL_TIME);
      if(dt > lastDeal) lastDeal = dt;
      int k = -1;
      for(int j = 0; j < n; j++) if(ids[j] == id) { k = j; break; }
      if(k < 0) { n++; ArrayResize(ids, n); ArrayResize(vin, n); ArrayResize(pnl, n); k = n - 1; ids[k] = id; vin[k] = 0; pnl[k] = 0; }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) vin[k] += HistoryDealGetDouble(d, DEAL_VOLUME);
      pnl[k] += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_SWAP);
   }
   for(int j = 0; j < n; j++)
   {
      if(vin[j] <= 0) continue;
      nTrades++;
      bool open = false;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
         if(PositionGetTicket(i) > 0 && PositionGetInteger(POSITION_IDENTIFIER) == ids[j]) { open = true; break; }
      if(!open && pnl[j] < -0.5 * vin[j] * LossPerLot(InpSlUsd)) nSL++;   // comme month.py : r < -0,5R = SL
   }
}

//--- gestion de la position ouverte : tiers, BE, fin de fenêtre ------------
void Manage(ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return;
   long   type = PositionGetInteger(POSITION_TYPE);
   int    d    = type == POSITION_TYPE_BUY ? 1 : -1;
   double vol  = PositionGetDouble(POSITION_VOLUME);
   double sl   = PositionGetDouble(POSITION_SL);
   double tp   = PositionGetDouble(POSITION_TP);
   long   pid  = PositionGetInteger(POSITION_IDENTIFIER);
   double R    = InpSlUsd;
   double e0   = tp - d * 3 * R;                  // TP final = clôture signal + 3R
   double px   = d == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   int    dg   = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   // fin de fenêtre
   int m = ParisMinutes(TimeCurrent());
   if(m < InpWinStartMin || m >= InpWinEndMin - InpFlattenMin)
   {
      if(trade.PositionClose(ticket)) Notify(StringFormat("Grok Desk : fin de fenêtre, position %s fermée à %.2f", d == 1 ? "ACHAT" : "VENTE", px));
      return;
   }
   if(tp <= 0) return;

   double initVol = InitialVolume(ticket, pid);
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double q1      = FloorLot(initVol / 3.0);
   bool   thirds  = q1 >= minLot;
   double closed  = initVol - vol;
   int    stage   = !thirds ? 0 : (closed >= 2 * q1 - 1e-8 ? 2 : (closed >= q1 - 1e-8 ? 1 : 0));
   double tp1 = e0 + d * R, tp2 = e0 + d * 2 * R;
   double be  = NormalizeDouble(e0, dg);
   bool   beSet = d * (sl - be) >= -_Point / 2;

   if(stage == 0 && d * (px - tp1) >= 0)
   {
      if(thirds && trade.PositionClosePartial(ticket, q1))
         Notify(StringFormat("Grok Desk : TP1 touché (%.2f), 1/3 fermé, SL au prix d'entrée %.2f", tp1, be));
      if(!thirds && !beSet) Notify(StringFormat("Grok Desk : TP1 touché (%.2f), SL au prix d'entrée %.2f", tp1, be));
      if(PositionSelectByTicket(ticket) && (thirds || !beSet)) trade.PositionModify(ticket, be, tp);
      return;
   }
   if(stage >= 1 && !beSet) trade.PositionModify(ticket, be, tp);     // BE pas encore posé (nouvel essai)
   if(stage == 1 && d * (px - tp2) >= 0)
   {
      double q2 = MathMin(q1, FloorLot(vol - minLot));
      if(q2 >= minLot && trade.PositionClosePartial(ticket, q2))
         Notify(StringFormat("Grok Desk : TP2 touché (%.2f), 2e tiers fermé", tp2));
   }
}

//--- signal sur la bougie M5 qui vient de clôturer --------------------------
void CheckSignal()
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M5, 1, 600, r);       // r[n-1] = bougie qui vient de clôturer
   if(n < InpAtrLen + 3) return;

   // ATR de Wilder ; atrPrev = ATR avant la bougie signal, atr = ATR après
   double atr = 0, atrPrev = 0, sum = 0, trLast = 0;
   for(int i = 0; i < n; i++)
   {
      double tr = i == 0 ? r[i].high - r[i].low
                         : MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i-1].close), MathAbs(r[i].low - r[i-1].close)));
      atrPrev = atr;
      if(i < InpAtrLen) { sum += tr; if(i == InpAtrLen - 1) atr = sum / InpAtrLen; }
      else atr = (atr * (InpAtrLen - 1) + tr) / InpAtrLen;
      trLast = tr;
   }
   if(atrPrev <= 0) return;

   // séance : nouvelle séance après un trou de plus de 30 min (pause quotidienne)
   int s = n - 1;
   while(s > 0 && r[s].time - r[s-1].time <= 30 * 60) s--;
   double px = 0;
   for(int i = s; i < n; i++) px += (r[i].high + r[i].low + r[i].close) / 3.0;
   double vwap = px / (n - s);
   datetime sessStart = r[s].time;

   // fenêtre horaire (heure d'ouverture de la bougie signal, en heure de Paris)
   int m = ParisMinutes(r[n-1].time);
   if(m < InpWinStartMin || m >= InpWinEndMin) return;
   if(m - InpWinStartMin < InpNoFirstMin) return;
   if((InpWinEndMin - m) - 5 < InpNoLastMin) return;

   int nTrades, nSL; datetime lastDeal;
   NightCounters(sessStart, nTrades, nSL, lastDeal);
   if(lastDeal >= r[n-1].time) return;   // comme month.py : pas de signal sur la bougie où un trade vient de se fermer
   if(nTrades >= InpMaxTrades) return;
   if(InpMaxSL > 0 && nSL >= InpMaxSL) return;

   double o = r[n-1].open, c = r[n-1].close;
   double rs = trLast / atrPrev;
   int d = 0;
   if(rs >= InpRangeAtr && c > vwap && c > o) d = 1;
   else if(InpAllowShort && rs >= InpRangeAtr && c < vwap && c < o) d = -1;
   if(d == 0) return;
   if(MathAbs(c - vwap) > InpMaxExtAtr * atr)
   {
      Print(StringFormat("Grok Desk : signal %s refusé, trop loin du VWAP (%.1f ATR)", d == 1 ? "ACHAT" : "VENTE", MathAbs(c - vwap) / atr));
      return;
   }

   // taille
   double R = InpSlUsd;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   string gv = "GD_peak_" + IntegerToString(InpMagic);
   double peak = GlobalVariableCheck(gv) ? MathMax(GlobalVariableGet(gv), eq) : eq;
   GlobalVariableSet(gv, peak);
   double lot;
   if(InpSizing == GD_FIXED_LOT) lot = InpFixedLot;
   else
   {
      double riskMoney = eq * InpRiskPct / 100.0;
      if(InpHalfRiskDD > 0 && peak - eq >= InpHalfRiskDD) riskMoney /= 2.0;
      double lpl = LossPerLot(R);
      if(lpl <= 0) { Print("Grok Desk : valeur du tick introuvable"); return; }
      lot = riskMoney / lpl;
   }
   lot = FloorLot(lot);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(lot < minLot) { Print(StringFormat("Grok Desk : lot %.3f < minimum %.2f, trade ignoré", lot, minLot)); return; }
   lot = MathMin(lot, maxLot);
   if(InpEquityFloor > 0 && eq - lot * LossPerLot(R) < InpEquityFloor)
   {
      Notify(StringFormat("Grok Desk : trade ignoré, un SL ferait passer l'equity sous le plancher %.0f", InpEquityFloor));
      return;
   }

   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double sl = NormalizeDouble(c - d * R, dg);
   double tp = NormalizeDouble(c + d * 3 * R, dg);
   bool ok = d == 1 ? trade.Buy(lot, _Symbol, 0, sl, tp, "GD nuit")
                    : trade.Sell(lot, _Symbol, 0, sl, tp, "GD nuit");
   if(ok)
      Notify(StringFormat("Grok Desk : %s %.2f lot XAUUSD · signal %.2f · SL %.2f · TP1 %.2f · TP2 %.2f · TP final %.2f",
             d == 1 ? "ACHAT" : "VENTE", lot, c, sl, c + d * R, c + d * 2 * R, tp));
   else
      Notify(StringFormat("Grok Desk : ordre refusé (%u %s)", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
}

//--- événements ---------------------------------------------------------
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints(50);
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("Grok Desk : attention, la règle a été validée sur XAUUSD uniquement");
   PrintFormat("Grok Desk prêt · %s · %s · heure de Paris maintenant %02d:%02d", _Symbol,
               InpSizing == GD_RISK_PCT ? StringFormat("risque %.2f %%", InpRiskPct) : StringFormat("lot fixe %.2f", InpFixedLot),
               ParisMinutes(TimeCurrent()) / 60, ParisMinutes(TimeCurrent()) % 60);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   ulong ticket;
   bool has = OurPosition(ticket);
   if(has) Manage(ticket);

   datetime bar = iTime(_Symbol, PERIOD_M5, 0);
   if(bar == 0 || bar == g_lastBar) return;
   g_lastBar = bar;
   if(!has && !OurPosition(ticket)) CheckSignal();
}
//+------------------------------------------------------------------+
