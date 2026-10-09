package com.codex.tgbotcontrol;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.util.SizeF;
import android.view.View;
import android.widget.RemoteViews;
import java.time.ZonedDateTime;
import java.time.Duration;
import java.util.LinkedHashMap;
import org.json.JSONArray;
import org.json.JSONObject;

/** Native, accessible RemoteViews. Rows never grow to fill the widget. */
final class AdaptivePowerViews {
    static final int INK=0xff1b2232,GREEN=0xff176b43,RED=0xffaf4334,MUTED=0xff69727d;
    static RemoteViews preview(Context c) {
        ZonedDateTime now=ZonedDateTime.now(PowerData.KYIV).withHour(14).withMinute(45);
        SharedPreferences prefs=c.getSharedPreferences("power_preview",Context.MODE_PRIVATE);
        SharedPreferences defaults=PowerData.prefs(c,0);
        prefs.edit().putString("name","Чутове").putString("group","2.2").putString("path","/example").putString("widget_theme",defaults.getString("widget_theme","light")).putString("widget_transparency",defaults.getString("widget_transparency","0")).apply();
        JSONObject data=new JSONObject();
        try {
            JSONArray slots=new JSONArray();int[] points={0,360,570,870,1080,1440};
            for(int i=0;i<points.length-1;i++)slots.put(new JSONObject().put("start",points[i]).put("end",points[i+1]).put("status",i%2==0?"on":"off"));
            data.put("date",now.toLocalDate().toString()).put("published",true).put("intervals",slots);
        }catch(Exception ignored){}
        RemoteViews view=make(c,0,prefs,data,new JSONObject(),now,320,150);
        view.setTextViewText(R.id.aw_updated,"Пример · выберите свой город и группу");
        return view;
    }
    static void publishPreview(Context c) {
        if(Build.VERSION.SDK_INT<35)return;
        try {
            AppWidgetManager.getInstance(c).setWidgetPreview(new android.content.ComponentName(c,PowerWidget.class),android.appwidget.AppWidgetProviderInfo.WIDGET_CATEGORY_HOME_SCREEN,preview(c));
        }catch(Exception e){android.util.Log.d("PowerWidget","Preview registration unavailable");}
    }
    static void update(Context c,int id) {
        AppWidgetManager manager=AppWidgetManager.getInstance(c);
        SharedPreferences p=PowerData.prefs(c,id);
        ZonedDateTime now=ZonedDateTime.now(PowerData.KYIV);
        JSONObject data=PowerData.cached(c,id,false);
        if(!today(data,now)) {
            JSONObject next=PowerData.cached(c,id,true);
            if(today(next,now))data=next;
        }
        if(!p.getString("group","").equals(data.optString("group"))||!p.getString("path","").equals(data.optString("location")))data=new JSONObject();
        Bundle options=manager.getAppWidgetOptions(id);
        RemoteViews views;
        if(Build.VERSION.SDK_INT>=31) {
            LinkedHashMap<SizeF,RemoteViews> layouts=new LinkedHashMap<>();
            java.util.ArrayList<SizeF> sizes=options.getParcelableArrayList(AppWidgetManager.OPTION_APPWIDGET_SIZES);
            if(sizes!=null&&!sizes.isEmpty()) {
                for(SizeF size:sizes) {if(layouts.size()==16)break;if(size==null||!Float.isFinite(size.getWidth())||!Float.isFinite(size.getHeight())||size.getWidth()<=0||size.getHeight()<=0)continue;layouts.put(size,make(c,id,p,data,PowerData.cached(c,id,true),now,size.getWidth(),size.getHeight()));}
            }
            views=layouts.isEmpty()?fallback(c,id,p,data,PowerData.cached(c,id,true),now,options):new RemoteViews(layouts);
        } else {
            views=fallback(c,id,p,data,PowerData.cached(c,id,true),now,options);
        }
        manager.updateAppWidget(id,views);
    }
    /** Older/OEM launchers may omit OPTION_APPWIDGET_SIZES even on Android 12+. */
    static RemoteViews fallback(Context c,int id,SharedPreferences p,JSONObject data,JSONObject tomorrow,ZonedDateTime now,Bundle options) {
        float minWidth=dimension(options,AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH,250);
        float maxWidth=dimension(options,AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH,minWidth);
        float minHeight=dimension(options,AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT,140);
        float maxHeight=dimension(options,AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT,minHeight);
        RemoteViews portrait=make(c,id,p,data,tomorrow,now,minWidth,maxHeight);
        RemoteViews landscape=make(c,id,p,data,tomorrow,now,maxWidth,minHeight);
        return new RemoteViews(landscape,portrait);
    }
    private static float dimension(Bundle options,String key,float fallback){int n=options.getInt(key,Math.round(fallback));return n>0&&n<=10000?n:fallback;}
    static boolean today(JSONObject d,ZonedDateTime now){return now.toLocalDate().toString().equals(d.optString("date"));}
    static RemoteViews make(Context c,int id,SharedPreferences p,JSONObject data,JSONObject tomorrow,ZonedDateTime now,float width,float height) {
        boolean compact=height<125||(width<260&&height<170),wide=width>=260,tall=height>=280;
        String theme=p.getString("widget_theme","light");
        boolean dark="dark".equals(theme)||("system".equals(theme)&&(c.getResources().getConfiguration().uiMode&android.content.res.Configuration.UI_MODE_NIGHT_MASK)==android.content.res.Configuration.UI_MODE_NIGHT_YES);
        int fg=dark?0xfff5f5f5:INK,muted=dark?0xffbbbbbb:MUTED,onColor=dark?0xff8ad7a2:GREEN,offColor=dark?0xffffa49a:RED;
        int transparency=0;try{transparency=Math.max(0,Math.min(100,Integer.parseInt(p.getString("widget_transparency","0"))));}catch(Exception ignored){}
        boolean dense=compact&&width>=100&&height>=100;
        boolean micro=height<42||width<100;
        boolean shortRow=height<100&&width>=100&&!micro;
        boolean narrowCompact=compact&&width<140&&!shortRow;
        RemoteViews v=new RemoteViews(c.getPackageName(),dense?R.layout.adaptive_dense:micro?R.layout.adaptive_micro:shortRow?R.layout.adaptive_short:narrowCompact?R.layout.adaptive_narrow_compact:width<140&&!compact?R.layout.adaptive_skinny:compact?R.layout.adaptive_compact:tall?R.layout.adaptive_tall:wide?R.layout.adaptive_wide:R.layout.adaptive_card);
        v.setImageViewResource(R.id.aw_background,dark?R.drawable.widget_surface_oled:R.drawable.widget_surface);
        v.setInt(R.id.aw_background,"setImageAlpha",Math.round((100-transparency)*255/100f));
        v.setTextColor(R.id.aw_title,fg);v.setTextColor(R.id.aw_time,fg);
        if(!micro&&(dense||width>=140||shortRow))v.setImageViewResource(R.id.aw_chevron,dark?R.drawable.widget_chevron_right_dark:R.drawable.widget_chevron_right);
        String name=p.getString("name","Выберите город").split(",")[0];
        v.setTextViewText(R.id.aw_title,name+" · "+p.getString("group","—"));
        boolean valid=today(data,now)&&data.optBoolean("published");
        JSONArray slots=valid?data.optJSONArray("intervals"):null;
        int minute=now.getHour()*60+now.getMinute();
        String current="",event="",time="",detail="По графику · время Киева",state="";
        boolean allDay=slots!=null&&slots.length()==1&&slots.optJSONObject(0)!=null
            &&slots.optJSONObject(0).optInt("start")==0&&slots.optJSONObject(0).optInt("end")==1440
            &&"on".equals(slots.optJSONObject(0).optString("status"));
        if(slots!=null) {
            for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s!=null&&s.optInt("start")<=minute&&minute<s.optInt("end"))current=s.optString("status");}
            for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s!=null&&s.optInt("start")>minute&&!s.optString("status").equals(current)){state=s.optString("status");time=PowerData.clock(s.optInt("start"));break;}}
            if(time.isEmpty()&&tomorrow.optBoolean("published")&&now.toLocalDate().plusDays(1).toString().equals(tomorrow.optString("date"))
                &&p.getString("group","").equals(tomorrow.optString("group"))&&p.getString("path","").equals(tomorrow.optString("location"))) {
                JSONArray next=tomorrow.optJSONArray("intervals");
                if(next!=null)for(int i=0;i<next.length();i++){JSONObject s=next.optJSONObject(i);if(s!=null&&!s.optString("status").equals(current)){state=s.optString("status");time=PowerData.clock(s.optInt("start"));detail="Завтра · время Киева";break;}}
            }
            event="on".equals(state)?"Включение":"off".equals(state)?"Отключение":"Уточняется";
            if(allDay){event="Сегодня без отключений";time="";state="on";detail="Свет по графику весь день";}
            else if(time.isEmpty()){event="on".equals(current)?"Свет до конца дня":"off".equals(current)?"Отключение до конца дня":"График уточняется";state=current;detail="По графику · время Киева";}
        } else {
            event=today(data,now)&&!data.optBoolean("published")?"Сегодня без графиков":"График не загружен";
            detail=today(data,now)?"Источник ещё не опубликовал расписание":"Проверьте соединение · нажмите для настройки";
        }
        int color="on".equals(state)?onColor:"off".equals(state)?offColor:muted;
        v.setTextViewText(R.id.aw_status,event);v.setTextColor(R.id.aw_status,color);v.setTextViewText(R.id.aw_time,time);
        v.setViewVisibility(R.id.aw_time,time.isEmpty()?View.GONE:View.VISIBLE);
        if(dense) {
            if(height<110){v.setTextViewTextSize(R.id.aw_time,android.util.TypedValue.COMPLEX_UNIT_SP,19);v.setTextViewTextSize(R.id.aw_detail,android.util.TypedValue.COMPLEX_UNIT_SP,8);}
            String label=slots==null?"Нет графика":allDay?"Свет весь день":"off".equals(current)?"Нет света":"on".equals(current)?"Свет есть":"Уточняется";
            String panelState=slots==null?"":current;
            v.setTextViewText(R.id.aw_status,label);
            v.setTextColor(R.id.aw_status,"on".equals(panelState)?onColor:"off".equals(panelState)?offColor:muted);
            v.setInt(R.id.aw_status_box,"setBackgroundResource",surface(dark,panelState,false));
            v.setImageViewResource(R.id.aw_icon,R.drawable.power_bolt);
            v.setInt(R.id.aw_icon,"setBackgroundResource","on".equals(panelState)?R.drawable.power_energy:"off".equals(panelState)?R.drawable.power_energy_off:R.drawable.power_energy_unknown);
            v.setTextViewText(R.id.aw_detail,time.isEmpty()?allDay?"Без отключений":slots==null?"Сегодня без графиков":"До конца дня":("on".equals(state)?"Включение":"off".equals(state)?"Отключение":"Уточняется")+(detail.startsWith("Завтра")?" завтра":width>=160?" по графику":""));
            v.setTextColor(R.id.aw_detail,muted);
            v.setContentDescription(R.id.aw_body,name+" "+p.getString("group","")+" "+label+" "+event+" "+time);
        } else if(compact||micro) {
            v.setTextViewText(R.id.aw_status,allDay?"Без отключений":event);
            if(compact&&!micro&&width<200&&!time.isEmpty()){
                v.setTextViewText(R.id.aw_status,"on".equals(state)?"Включение":"off".equals(state)?"Откл.":"Уточняется");
                v.setTextViewTextSize(R.id.aw_time,android.util.TypedValue.COMPLEX_UNIT_SP,22);
                v.setTextViewTextSize(R.id.aw_status,android.util.TypedValue.COMPLEX_UNIT_SP,11);
            }
            if(shortRow){v.setTextViewTextSize(R.id.aw_time,android.util.TypedValue.COMPLEX_UNIT_SP,16);v.setTextViewTextSize(R.id.aw_status,android.util.TypedValue.COMPLEX_UNIT_SP,10);}
            if(narrowCompact){v.setTextViewTextSize(R.id.aw_time,android.util.TypedValue.COMPLEX_UNIT_SP,20);v.setTextViewTextSize(R.id.aw_status,android.util.TypedValue.COMPLEX_UNIT_SP,11);}
            if(micro&&width>=100&&width<140&&!time.isEmpty())v.setTextViewText(R.id.aw_status,"on".equals(state)?"Вкл.":"off".equals(state)?"Откл.":event);
            if(width<100){v.setTextViewText(R.id.aw_status,allDay?"Свет":slots==null?"Нет данных":"off".equals(current)?"Нет света":"Свет");v.setTextViewTextSize(R.id.aw_status,android.util.TypedValue.COMPLEX_UNIT_SP,10);v.setViewVisibility(R.id.aw_status,time.isEmpty()?View.VISIBLE:View.GONE);v.setTextViewTextSize(R.id.aw_time,android.util.TypedValue.COMPLEX_UNIT_SP,12);}
            v.setContentDescription(R.id.aw_body,name+" "+p.getString("group","")+" "+event+" "+time+" "+detail);
        } else {
            v.setInt(R.id.aw_status_box,"setBackgroundResource",surface(dark,state,false));
            v.setImageViewResource(R.id.aw_icon,R.drawable.power_bolt);
            v.setInt(R.id.aw_icon,"setBackgroundResource","on".equals(state)?R.drawable.power_energy:"off".equals(state)?R.drawable.power_energy_off:R.drawable.power_energy_unknown);
            v.setTextViewText(R.id.aw_detail,detail);
            v.setTextColor(R.id.aw_detail,muted);v.setTextColor(R.id.aw_more,muted);
            v.setImageViewResource(R.id.aw_refresh,dark?R.drawable.widget_refresh_dark:R.drawable.widget_refresh);
            v.removeAllViews(R.id.aw_rows);
            if(tall)v.setViewVisibility(R.id.aw_all_day_art,allDay&&height>=360&&width>=140?View.VISIBLE:View.GONE);
            if(tall&&width>=140){v.setImageViewResource(R.id.aw_all_day_icon,dark?R.drawable.widget_lightbulb_dark:R.drawable.widget_lightbulb);v.setTextColor(R.id.aw_all_day_range,onColor);v.setTextColor(R.id.aw_all_day_note,muted);}
            if(slots!=null&&!allDay&&width>=140) {
                String currentLabel="off".equals(current)?"Нет света":"on".equals(current)?"Свет есть":"Уточняется";
                v.setTextViewText(R.id.aw_status,currentLabel);
                v.setTextColor(R.id.aw_status,"off".equals(current)?offColor:"on".equals(current)?onColor:muted);
                v.setInt(R.id.aw_status_box,"setBackgroundResource",surface(dark,current,false));
                v.setImageViewResource(R.id.aw_icon,R.drawable.power_bolt);
                v.setInt(R.id.aw_icon,"setBackgroundResource","on".equals(current)?R.drawable.power_energy:"off".equals(current)?R.drawable.power_energy_off:R.drawable.power_energy_unknown);
                if(tall)v.setViewVisibility(R.id.aw_time,View.GONE);
                v.setTextViewText(R.id.aw_detail,time.isEmpty()?"По графику · время Киева":"По графику · "+event+" в "+time+(detail.startsWith("Завтра")?" завтра":""));
                if(!tall&&width<240&&!time.isEmpty())v.setTextViewText(R.id.aw_detail,(detail.startsWith("Завтра")?"Завтра · ":"По графику · ")+("on".equals(state)?"Вкл. ":"off".equals(state)?"Откл. ":"")+time);
            }
            int capacity=tall?Math.max(1,Math.min(12,(int)((height-(width<160?220:170))/45))):0;
            int total=slots==null?0:slots.length();
            int begin=0;
            if(total>capacity&&capacity>0){for(int i=0;i<total;i++){JSONObject s=slots.optJSONObject(i);if(s!=null&&s.optInt("end")>minute){begin=Math.max(0,Math.min(i,total-capacity));break;}}}
            int shown=0;
            if(!allDay&&capacity>0&&slots!=null)for(int i=begin;i<Math.min(total,begin+capacity);i++){
                JSONObject s=slots.optJSONObject(i);if(s==null)continue;
                RemoteViews row=new RemoteViews(c.getPackageName(),R.layout.adaptive_row);
                String status=s.optString("status");boolean on="on".equals(status),off="off".equals(status),active=s.optInt("start")<=minute&&minute<s.optInt("end");
                String interval=PowerData.clock(s.optInt("start"))+(width<160?"–":" – ")+PowerData.clock(s.optInt("end"));
                row.setTextViewText(R.id.ar_time,interval);row.setTextColor(R.id.ar_time,s.optInt("end")<=minute?muted:fg);
                row.setInt(R.id.ar_body,"setBackgroundResource",surface(dark,status,active));
                row.setImageViewResource(R.id.ar_icon,icon(dark,status));
                row.setTextViewText(R.id.ar_label,on?"Свет есть":off?"Без света":"Уточняется");
                row.setTextColor(R.id.ar_label,on?onColor:off?offColor:muted);
                row.setViewVisibility(R.id.ar_label,width>=240?View.VISIBLE:View.GONE);
                row.setViewVisibility(R.id.ar_icon,on||off?View.VISIBLE:View.INVISIBLE);
                if(width<160){row.setTextViewTextSize(R.id.ar_time,android.util.TypedValue.COMPLEX_UNIT_SP,width<140?11:12);row.setTextViewText(R.id.ar_time,PowerData.clock(s.optInt("start"))+"–"+PowerData.clock(s.optInt("end")));if(width<140)row.setViewVisibility(R.id.ar_icon,View.GONE);}
                if(active){android.text.SpannableString emphasis=new android.text.SpannableString(interval);emphasis.setSpan(new android.text.style.StyleSpan(android.graphics.Typeface.BOLD),0,interval.length(),android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);row.setTextViewText(R.id.ar_time,emphasis);}
                row.setContentDescription(R.id.ar_body,interval+(on?" · свет по графику":off?" · отключение":" · уточняется")+(active?" · сейчас":""));
                v.addView(R.id.aw_rows,row);shown++;
            }
            v.setTextViewText(R.id.aw_more,shown>0&&shown<total?"Ещё "+(total-shown)+" · полный день по нажатию":"");
            v.setViewVisibility(R.id.aw_more,shown>0&&shown<total?View.VISIBLE:View.GONE);
            boolean chart=wide&&!tall&&slots!=null;
            v.setViewVisibility(R.id.aw_timeline,chart?View.VISIBLE:View.GONE);
            if(chart)v.setImageViewBitmap(R.id.aw_timeline,timeline(slots,minute,dark));
            String updated=data.optString("sourceUpdated"),saved="";
            try{if(data.optBoolean("stale")||Duration.between(ZonedDateTime.parse(data.getString("fetchedAt")),now).toMinutes()>45)saved=" · сохранено";}catch(Exception ignored){}
            v.setTextViewText(R.id.aw_updated,"Без Світла"+(updated.isEmpty()?"":" · "+updated)+saved);
            v.setTextColor(R.id.aw_updated,muted);
            v.setOnClickPendingIntent(R.id.aw_refresh,PendingIntent.getBroadcast(c,id,new Intent(c,PowerWidget.class).setAction(PowerWidget.REFRESH),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
        }
        Intent open=new Intent(c,PowerActivity.class).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.aw_body,PendingIntent.getActivity(c,id,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
        return v;
    }
    private static int surface(boolean dark,String state,boolean active){
        if("on".equals(state))return dark?(active?R.drawable.widget_on_dark_active:R.drawable.widget_on_dark):(active?R.drawable.widget_on_active:R.drawable.widget_on);
        if("off".equals(state))return dark?(active?R.drawable.widget_off_dark_active:R.drawable.widget_off_dark):(active?R.drawable.widget_off_active:R.drawable.widget_off);
        return dark?R.drawable.widget_neutral_dark:R.drawable.widget_neutral;
    }
    private static int icon(boolean dark,String state){
        if("on".equals(state))return dark?R.drawable.widget_lightbulb_dark:R.drawable.widget_lightbulb;
        if("off".equals(state))return dark?R.drawable.widget_bulb_off_dark:R.drawable.widget_bulb_off;
        return R.drawable.widget_flash_on;
    }
    private static android.graphics.Bitmap timeline(JSONArray slots,int minute,boolean dark) {
        android.graphics.Bitmap b=android.graphics.Bitmap.createBitmap(700,90,android.graphics.Bitmap.Config.ARGB_8888);
        android.graphics.Canvas canvas=new android.graphics.Canvas(b);
        android.graphics.Paint p=new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s==null)continue;p.setColor("on".equals(s.optString("status"))?0xff79af8b:"off".equals(s.optString("status"))?0xffd68478:0xffbdb8b0);canvas.drawRect(8+s.optInt("start")*684f/1440,12,8+s.optInt("end")*684f/1440,44,p);}
        p.setColor(dark?0xfff5f5f5:INK);p.setStrokeWidth(3);float x=8+minute*684f/1440;canvas.drawLine(x,6,x,50,p);
        p.setColor(dark?0xffbbbbbb:MUTED);p.setTextSize(23);
        for(int h=0;h<=24;h+=6){p.setTextAlign(h==0?android.graphics.Paint.Align.LEFT:h==24?android.graphics.Paint.Align.RIGHT:android.graphics.Paint.Align.CENTER);canvas.drawText(String.format(java.util.Locale.ROOT,"%02d",h),8+h*684f/24,80,p);}
        return b;
    }
}
