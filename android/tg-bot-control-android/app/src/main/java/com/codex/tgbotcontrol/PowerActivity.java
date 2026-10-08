package com.codex.tgbotcontrol;

import android.app.Activity;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.widget.*;
import android.view.View;
import android.view.ViewGroup;
import android.net.Uri;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PowerActivity extends Activity {
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private LinearLayout body,results;
    private TextView status,graph;
    private EditText search;
    private Spinner groups;
    private String selectedPath="",selectedName="";
    private int widgetId,request=0;
    private boolean settingText=false;
    private Runnable searchTask;
    private String[] groupValues;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        widgetId=getIntent().getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,AppWidgetManager.INVALID_APPWIDGET_ID);
        setResult(RESULT_CANCELED);
        ScrollView scroll=new ScrollView(this);
        body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(20),dp(20),dp(20),dp(20));body.setBackgroundColor(0xfffbf8f3);
        body.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(dp(20),dp(20)+insets.getSystemWindowInsetTop(),dp(20),dp(20)+insets.getSystemWindowInsetBottom());return insets;});
        scroll.addView(body);setContentView(scroll);
        text("Отключения света",28);
        text("Полтавская область · расписание по группе\nАварийные отключения могут отличаться от графика.",14);
        search=new EditText(this);search.setSingleLine(true);search.setHint("Населённый пункт, например Чутове");body.addView(search);
        results=new LinearLayout(this);results.setOrientation(LinearLayout.VERTICAL);body.addView(results);
        groups=new Spinner(this);groupValues=new String[13];groupValues[0]="Выберите группу";
        for(int i=1;i<=12;i++)groupValues[i]=((i+1)/2)+"."+(i%2==1?1:2);
        groups.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,groupValues));body.addView(groups);
        status=text("Выберите населённый пункт и свою группу отключений.",14);
        button("Сохранить и показать график",this::save);
        button("Обновить",()->load(false));
        button("График на завтра",()->load(true));
        if(widgetId==AppWidgetManager.INVALID_APPWIDGET_ID) {
            button("Добавить виджет 1×2 · следующее событие",()->pin(PowerCompactWidget.class));
            button("Добавить виджет 4×2 · весь день",()->pin(PowerWidget.class));
        }
        graph=text("",18);
        button("Открыть источник · Без Світла",()->{
            if(!selectedPath.isEmpty())startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse("https://bezsvitla.com.ua"+selectedPath)));
        });
        int id=widgetId==AppWidgetManager.INVALID_APPWIDGET_ID?0:widgetId;
        SharedPreferences p=PowerData.prefs(this,id);
        if(!p.contains("path"))p=PowerData.prefs(this,0);
        selectedPath=p.getString("path","");selectedName=p.getString("name","");
        search.setText(selectedName);
        for(int i=1;i<groupValues.length;i++)if(groupValues[i].equals(p.getString("group","")))groups.setSelection(i);
        groups.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            private int previous=groups.getSelectedItemPosition();
            public void onItemSelected(AdapterView<?> parent,View view,int position,long row){
                if(position!=previous){previous=position;request++;graph.setText("");status.setText("Группа изменена. Сохраните выбор или обновите график.");}
            }
            public void onNothingSelected(AdapterView<?> parent){}
        });
        search.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){
                if(settingText)return;selectedPath="";selectedName="";request++;results.removeAllViews();
                if(searchTask!=null)main.removeCallbacks(searchTask);
                String q=s.toString().trim();int token=request;
                if(q.length()<2)return;
                searchTask=()->worker.execute(()->{
                    try {
                        JSONObject response=PowerData.get(PowerData.server(PowerActivity.this)+"/power/locations?q="+PowerData.encode(q));
                        JSONArray items=response.getJSONArray("locations");
                        main.post(()->{if(token!=request||isFinishing())return;results.removeAllViews();
                            status.setText(items.length()==0?"Ничего не найдено в Полтавской области.":"Выберите населённый пункт из списка.");
                            for(int i=0;i<items.length();i++) {
                                JSONObject item=items.optJSONObject(i);if(item==null)continue;
                                Button choice=new Button(PowerActivity.this);choice.setText(item.optString("name"));
                                choice.setOnClickListener(v->{selectedPath=item.optString("path");selectedName=item.optString("name");settingText=true;search.setText(selectedName);settingText=false;request++;results.removeAllViews();status.setText("Населённый пункт выбран. Укажите группу своего дома.");});results.addView(choice);
                            }
                        });
                    }catch(Exception e){main.post(()->{if(token==request&&!isFinishing())status.setText("Поиск недоступен. Проверьте интернет и обновление сервера.");});}
                });
                main.postDelayed(searchTask,450);
            }
            public void afterTextChanged(Editable e){}
        });
        if(!selectedPath.isEmpty()&&groups.getSelectedItemPosition()>0)load(false);
    }
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private void pin(Class<?> provider){
        if(!valid())return;savePreferences();
        AppWidgetManager manager=AppWidgetManager.getInstance(this);
        if(manager.isRequestPinAppWidgetSupported())manager.requestPinAppWidget(new ComponentName(this,provider),null,null);
        else status.setText("Удерживайте свободное место на главном экране → Виджеты → Abstergo.");
    }
    private TextView text(String s,int size){TextView v=new TextView(this);v.setText(s);v.setTextSize(size);v.setTextColor(0xff32291f);v.setPadding(0,dp(10),0,dp(10));body.addView(v);return v;}
    private void button(String title,Runnable action){Button b=new Button(this);b.setText(title);b.setOnClickListener(v->action.run());body.addView(b,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));}
    private boolean valid(){if(selectedPath.isEmpty()||groups.getSelectedItemPosition()==0){status.setText("Сначала выберите населённый пункт из поиска и группу.");return false;}return true;}
    private int dataId(){return widgetId==AppWidgetManager.INVALID_APPWIDGET_ID?0:widgetId;}
    private void savePreferences(){
        SharedPreferences p=PowerData.prefs(this,dataId());String group=groupValues[groups.getSelectedItemPosition()];
        SharedPreferences.Editor edit=p.edit();
        if(!group.equals(p.getString("group",""))||!selectedPath.equals(p.getString("path","")))edit.remove("today").remove("tomorrow");
        edit.putString("path",selectedPath).putString("name",selectedName).putString("group",group).putString("server",PowerData.server(this)).apply();
    }
    private void save(){
        if(!valid())return;savePreferences();
        if(widgetId!=AppWidgetManager.INVALID_APPWIDGET_ID){
            PowerWidget.render(this,widgetId);PowerWidget.refresh(this);
            setResult(RESULT_OK,new Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,widgetId));finish();
        }else {status.setText("Выбор сохранён.");load(false);}
    }
    private void load(boolean tomorrow){
        if(!valid())return;savePreferences();final int id=dataId();final int token=++request;
        display(PowerData.cached(this,id,tomorrow),tomorrow,true);status.setText("Обновляю график…");
        worker.execute(()->{
            try {JSONObject data=PowerData.fetch(this,id,tomorrow);main.post(()->{if(token==request&&!isFinishing()){display(data,tomorrow,data.optBoolean("stale"));status.setText(data.optBoolean("stale")?"Источник недоступен · сохранённые данные":"График обновлён");}});}
            catch(Exception e){main.post(()->{if(token==request&&!isFinishing())status.setText("Нет соединения с графиками. Показаны сохранённые данные, если они есть.");});}
        });
    }
    private void display(JSONObject data,boolean tomorrow,boolean cached){
        String expected=java.time.ZonedDateTime.now(PowerData.KYIV).toLocalDate().plusDays(tomorrow?1:0).toString();
        if(!expected.equals(data.optString("date"))||!data.optBoolean("published")){graph.setText((tomorrow?"Завтра":"Сегодня")+": график не опубликован или ещё не загружен.");return;}
        StringBuilder lines=new StringBuilder((tomorrow?"Завтра":"Сегодня")+" · "+expected+"\n");
        JSONArray slots=data.optJSONArray("intervals");
        if(slots!=null)for(int i=0;i<slots.length();i++){JSONObject slot=slots.optJSONObject(i);if(slot!=null)lines.append(PowerData.clock(slot.optInt("start"))).append("–").append(PowerData.clock(slot.optInt("end"))).append("  ").append(PowerData.intervalLabel(slot.optString("status"))).append('\n');}
        lines.append("\nОбновлено источником: ").append(data.optString("sourceUpdated","не указано"));if(cached)lines.append("\nСохранённый график");graph.setText(lines.toString());
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);recreate();}
    @Override protected void onDestroy(){request++;if(searchTask!=null)main.removeCallbacks(searchTask);worker.shutdownNow();super.onDestroy();}
}
