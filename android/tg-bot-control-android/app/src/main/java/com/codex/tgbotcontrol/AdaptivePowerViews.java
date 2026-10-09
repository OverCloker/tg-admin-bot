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
    static final int INK=0xff1b2232,GREEN=0xff237244,RED=0xffa6312b,MUTED=0xff746e68;
    static RemoteViews preview(Context c) {
        ZonedDateTime now=ZonedDateTime.now(PowerData.KYIV).withHour(14).withMinute(45);
        SharedPreferences prefs=c.getSharedPreferences("power_preview",Context.MODE_PRIVATE);
        prefs.edit().putString("name","Чутове").putString("group","2.2").putString("path","/example").apply();
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
                for(SizeF size:sizes) {if(layouts.size()==16)break;layouts.put(size,make(c,id,p,data,PowerData.cached(c,id,true),now,size.getWidth(),size.getHeight()));}
            } else {
                for(SizeF size:new SizeF[]{new SizeF(110,50),new SizeF(110,150),new SizeF(260,150),new SizeF(110,280),new SizeF(260,280)})
                    layouts.put(size,make(c,id,p,data,PowerData.cached(c,id,true),now,size.getWidth(),size.getHeight()));
            }
            views=new RemoteViews(layouts);
        } else {
            boolean landscape=c.getResources().getConfiguration().orientation==android.content.res.Configuration.ORIENTATION_LANDSCAPE;
            float width=options.getInt(landscape?AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH:AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH,280);
            float height=options.getInt(landscape?AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT:AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT,150);
            views=make(c,id,p,data,PowerData.cached(c,id,true),now,width,height);
        }
        manager.updateAppWidget(id,views);
    }
    static boolean today(JSONObject d,ZonedDateTime now){return now.toLocalDate().toString().equals(d.optString("date"));}
    static RemoteViews make(Context c,int id,SharedPreferences p,JSONObject data,JSONObject tomorrow,ZonedDateTime now,float width,float height) {
        boolean compact=height<125,wide=width>=260,tall=height>=280;
        boolean micro=height<65||width<100||(width<140&&height<160);
        RemoteViews v=new RemoteViews(c.getPackageName(),micro?R.layout.adaptive_micro:width<140&&!compact?R.layout.adaptive_skinny:compact?R.layout.adaptive_compact:tall?R.layout.adaptive_tall:wide?R.layout.adaptive_wide:R.layout.adaptive_card);
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
        int color="on".equals(state)?GREEN:"off".equals(state)?RED:MUTED;
        v.setTextViewText(R.id.aw_status,event);v.setTextColor(R.id.aw_status,color);v.setTextViewText(R.id.aw_time,time);
        v.setViewVisibility(R.id.aw_time,time.isEmpty()?View.GONE:View.VISIBLE);
        if(compact||micro) {
            v.setTextViewText(R.id.aw_status,allDay?"Без отключений":event);
            if(micro&&width>=100&&width<140&&!time.isEmpty())v.setTextViewText(R.id.aw_status,"on".equals(state)?"Вкл.":"off".equals(state)?"Откл.":event);
            if(width<100){v.setTextViewText(R.id.aw_status,allDay?"Свет":slots==null?"Нет данных":"off".equals(current)?"Нет света":"Свет");v.setTextViewTextSize(R.id.aw_status,android.util.TypedValue.COMPLEX_UNIT_SP,10);v.setViewVisibility(R.id.aw_status,time.isEmpty()?View.VISIBLE:View.GONE);v.setTextViewTextSize(R.id.aw_time,android.util.TypedValue.COMPLEX_UNIT_SP,12);}
            v.setContentDescription(R.id.aw_body,name+" "+p.getString("group","")+" "+event+" "+time+" "+detail);
        } else {
            v.setInt(R.id.aw_status_box,"setBackgroundResource","on".equals(state)?R.drawable.widget_on:"off".equals(state)?R.drawable.widget_off:R.drawable.widget_neutral);
            v.setImageViewResource(R.id.aw_icon,"off".equals(state)?R.drawable.widget_bulb_off:"on".equals(state)?R.drawable.widget_lightbulb:R.drawable.widget_flash_on);
            v.setTextViewText(R.id.aw_detail,detail);
            v.removeAllViews(R.id.aw_rows);
            if(tall)v.setViewVisibility(R.id.aw_all_day_art,allDay&&height>=360&&width>=140?View.VISIBLE:View.GONE);
            if(tall&&slots!=null&&!allDay) {
                String currentLabel="off".equals(current)?"Сейчас нет света":"on".equals(current)?"Сейчас есть свет":"Уточняется";
                v.setTextViewText(R.id.aw_status,currentLabel);
                v.setTextColor(R.id.aw_status,"off".equals(current)?RED:"on".equals(current)?GREEN:MUTED);
                v.setInt(R.id.aw_status_box,"setBackgroundResource","off".equals(current)?R.drawable.widget_off:"on".equals(current)?R.drawable.widget_on:R.drawable.widget_neutral);
                v.setImageViewResource(R.id.aw_icon,"off".equals(current)?R.drawable.widget_bulb_off:R.drawable.widget_lightbulb);
                v.setViewVisibility(R.id.aw_time,View.GONE);
                v.setTextViewText(R.id.aw_detail,time.isEmpty()?"Сегодня · время Киева":event+" в "+time+(detail.startsWith("Завтра")?" завтра":""));
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
                row.setTextViewText(R.id.ar_time,interval);row.setTextColor(R.id.ar_time,s.optInt("end")<=minute?MUTED:INK);
                row.setInt(R.id.ar_body,"setBackgroundResource",on?(active?R.drawable.widget_on_active:R.drawable.widget_on):off?(active?R.drawable.widget_off_active:R.drawable.widget_off):R.drawable.widget_neutral);
                row.setImageViewResource(R.id.ar_icon,off?R.drawable.widget_bulb_off:R.drawable.widget_lightbulb);
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
            if(chart)v.setImageViewBitmap(R.id.aw_timeline,timeline(slots,minute));
            String updated=data.optString("sourceUpdated"),saved="";
            try{if(data.optBoolean("stale")||Duration.between(ZonedDateTime.parse(data.getString("fetchedAt")),now).toMinutes()>45)saved=" · сохранено";}catch(Exception ignored){}
            v.setTextViewText(R.id.aw_updated,"Без Світла"+(updated.isEmpty()?"":" · "+updated)+saved);
            v.setTextColor(R.id.aw_updated,MUTED);
            v.setOnClickPendingIntent(R.id.aw_refresh,PendingIntent.getBroadcast(c,id,new Intent(c,PowerWidget.class).setAction(PowerWidget.REFRESH),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
        }
        Intent open=new Intent(c,PowerActivity.class).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.aw_body,PendingIntent.getActivity(c,id,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
        return v;
    }
    private static android.graphics.Bitmap timeline(JSONArray slots,int minute) {
        android.graphics.Bitmap b=android.graphics.Bitmap.createBitmap(700,90,android.graphics.Bitmap.Config.ARGB_8888);
        android.graphics.Canvas canvas=new android.graphics.Canvas(b);
        android.graphics.Paint p=new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s==null)continue;p.setColor("on".equals(s.optString("status"))?0xff79af8b:"off".equals(s.optString("status"))?0xffd68478:0xffbdb8b0);canvas.drawRect(8+s.optInt("start")*684f/1440,12,8+s.optInt("end")*684f/1440,44,p);}
        p.setColor(INK);p.setStrokeWidth(3);float x=8+minute*684f/1440;canvas.drawLine(x,6,x,50,p);
        p.setColor(MUTED);p.setTextSize(23);
        for(int h=0;h<=24;h+=6){p.setTextAlign(h==0?android.graphics.Paint.Align.LEFT:h==24?android.graphics.Paint.Align.RIGHT:android.graphics.Paint.Align.CENTER);canvas.drawText(String.format(java.util.Locale.ROOT,"%02d",h),8+h*684f/24,80,p);}
        return b;
    }
}
