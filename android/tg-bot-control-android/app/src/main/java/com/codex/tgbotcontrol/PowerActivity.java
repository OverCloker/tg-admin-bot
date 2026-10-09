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
    private Spinner widgetTheme;
    private SeekBar widgetTransparency;
    private TextView transparencyLabel;
    private LinearLayout addressEditor,scheduleRows,hero,previewHost;
    private TextView addressLabel,heroTitle,heroDetail,heroTime,updatedLabel,addressHint;
    private ImageView heroIcon;
    private Button todayTab,tomorrowTab;
    private final Button[] themeTabs=new Button[3];
    private boolean showingTomorrow=false;
    private String selectedPath="",selectedName="";
    private int widgetId,request=0;
    private boolean settingText=false;
    private Runnable searchTask;
    private String[] groupValues;
    private String observedGroup="";
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        AdaptivePowerViews.publishPreview(this);
        widgetId=getIntent().getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,AppWidgetManager.INVALID_APPWIDGET_ID);
        setResult(RESULT_CANCELED);
        buildScreen();
        int id=dataId();
        SharedPreferences p=PowerData.prefs(this,id);
        if(!p.contains("path"))p=PowerData.prefs(this,0);
        String style=p.getString("widget_theme","light");
        widgetTheme.setSelection("system".equals(style)?0:"dark".equals(style)?2:1);
        try{widgetTransparency.setProgress(Math.max(0,Math.min(100,Integer.parseInt(p.getString("widget_transparency","0")))));}catch(Exception ignored){}
        updateThemeButtons();
        selectedPath=p.getString("path","");selectedName=p.getString("name","");
        search.setText(selectedName);
        String savedGroup=p.getString("group","");
        if(!savedGroup.isEmpty()&&!java.util.Arrays.asList(groupValues).contains(savedGroup)){
            groupValues=java.util.Arrays.copyOf(groupValues,groupValues.length+1);groupValues[groupValues.length-1]=savedGroup;
            groups.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,groupValues));
        }
        for(int i=1;i<groupValues.length;i++)if(groupValues[i].equals(p.getString("group","")))groups.setSelection(i);
        observedGroup=groupValues[groups.getSelectedItemPosition()];
        updateAddress();
        addressEditor.setVisibility(selectedPath.isEmpty()?View.VISIBLE:View.GONE);
        if(!selectedPath.isEmpty()&&groups.getSelectedItemPosition()>0)status.setText("");
        groups.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onItemSelected(AdapterView<?> parent,View view,int position,long row){
                if(position!=groups.getSelectedItemPosition())return;
                String code=groupValues[position];
                if(!code.equals(observedGroup)){observedGroup=code;request++;clearSchedule();updateAddress();status.setText("Группа изменена. Сохраните выбор или обновите график.");}
            }
            public void onNothingSelected(AdapterView<?> parent){}
        });
        search.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){
                if(settingText)return;selectedPath="";selectedName="";request++;results.removeAllViews();clearSchedule();updateAddress();
                if(searchTask!=null)main.removeCallbacks(searchTask);
                String q=s.toString().trim();int token=request;
                if(q.length()<2)return;
                searchTask=()->worker.execute(()->{
                    try {
                        JSONObject response=PowerData.get(PowerData.server(PowerActivity.this)+"/power/locations?q="+PowerData.encode(q));
                        JSONArray items=response.getJSONArray("locations");
                        main.post(()->{if(token!=request||isFinishing())return;results.removeAllViews();
                            status.setText(items.length()==0?"Населённый пункт не найден на сайте.":"Выберите населённый пункт из списка.");
                            for(int i=0;i<items.length();i++) {
                                JSONObject item=items.optJSONObject(i);if(item==null)continue;
                                Button choice=PowerStyle.button(PowerActivity.this,item.optString("name"),false);
                                choice.setOnClickListener(v->{selectedPath=item.optString("path");selectedName=item.optString("name");settingText=true;search.setText(selectedName);settingText=false;request++;results.removeAllViews();observedGroup=groupValues[0];groups.setSelection(0);clearSchedule();updateAddress();loadGroups();});results.addView(choice,spaced(6));
                            }
                        });
                    }catch(Exception e){main.post(()->{if(token==request&&!isFinishing())status.setText("Поиск недоступен. Проверьте интернет и обновление сервера.");});}
                });
                main.postDelayed(searchTask,450);
            }
            public void afterTextChanged(Editable e){}
        });
        if(!isDesignPreview()&&!selectedPath.isEmpty()&&groups.getSelectedItemPosition()>0)load(false);
        if(!isDesignPreview()&&!selectedPath.isEmpty())loadGroups();
        updateWidgetPreview();
    }
    private void buildScreen(){
        getWindow().setStatusBarColor(PowerStyle.PAGE);getWindow().setNavigationBarColor(PowerStyle.PAGE);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(PowerStyle.PAGE);
        body=column();body.setPadding(dp(20),dp(12),dp(20),dp(20));
        body.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(dp(20),dp(12)+insets.getSystemWindowInsetTop(),dp(20),dp(20)+insets.getSystemWindowInsetBottom());return insets;});
        scroll.addView(body);setContentView(scroll);
        body.addView(PowerStyle.label(this,"Свет",30,PowerStyle.INK,true));
        TextView intro=PowerStyle.label(this,"Расписание по вашей группе. Аварийные отключения могут отличаться от графика.",12,PowerStyle.MUTED,false);body.addView(intro,spaced(6));
        LinearLayout address=row();address.setPadding(dp(12),dp(6),dp(12),dp(6));PowerStyle.clickable(this,address,PowerStyle.ON,14);
        address.addView(PowerStyle.icon(this,R.drawable.power_map_pin,PowerStyle.GREEN),new LinearLayout.LayoutParams(dp(22),dp(22)));
        addressLabel=PowerStyle.label(this,"Выберите населённый пункт",15,PowerStyle.INK,true);
        LinearLayout.LayoutParams addressText=new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1);addressText.setMargins(dp(10),0,dp(10),0);address.addView(addressLabel,addressText);
        address.addView(PowerStyle.icon(this,R.drawable.power_pencil,PowerStyle.GREEN),new LinearLayout.LayoutParams(dp(22),dp(22)));
        address.setMinimumHeight(dp(44));address.setContentDescription("Изменить населённый пункт и группу");
        address.setOnClickListener(v->{addressEditor.setVisibility(addressEditor.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE);if(addressEditor.getVisibility()==View.VISIBLE)search.requestFocus();});body.addView(address,spaced(14));
        addressEditor=column();body.addView(addressEditor,spaced(8));
        addressEditor.addView(PowerStyle.label(this,"Населённый пункт",12,PowerStyle.MUTED,false));
        search=new EditText(this);search.setSingleLine(true);search.setTextSize(16);search.setTextColor(PowerStyle.INK);search.setHintTextColor(PowerStyle.MUTED);search.setHint("Введите город или село");search.setPadding(dp(12),dp(10),dp(12),dp(10));search.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,12));search.setMinHeight(dp(48));search.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_DONE);addressEditor.addView(search,spaced(6));
        results=column();addressEditor.addView(results);
        addressHint=PowerStyle.label(this,"Выберите населённый пункт из результатов поиска.",12,PowerStyle.MUTED,false);addressEditor.addView(addressHint,spaced(6));
        addressEditor.addView(PowerStyle.label(this,"Группа отключений",12,PowerStyle.MUTED,false),spaced(12));
        groups=new Spinner(this);groups.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,12));groups.setPadding(dp(6),0,dp(6),0);groups.setMinimumHeight(dp(48));groupValues=new String[13];groupValues[0]="Выберите группу";
        for(int i=1;i<=12;i++)groupValues[i]=((i+1)/2)+"."+(i%2==1?1:2);
        groups.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,groupValues));
        LinearLayout groupRow=row();groupRow.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,12));groupRow.addView(groups,new LinearLayout.LayoutParams(0,dp(48),1));
        ImageView groupArrow=PowerStyle.icon(this,R.drawable.widget_chevron_right,PowerStyle.MUTED);groupArrow.setRotation(90);groupArrow.setPadding(dp(8),dp(8),dp(8),dp(8));groupArrow.setOnClickListener(v->groups.performClick());groupArrow.setContentDescription("Открыть группы");groupArrow.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);groupRow.addView(groupArrow,new LinearLayout.LayoutParams(dp(44),dp(48)));addressEditor.addView(groupRow,spaced(6));
        Button saveAddress=PowerStyle.button(this,"Сохранить и показать график",true);saveAddress.setOnClickListener(v->{if(valid()){addressEditor.setVisibility(View.GONE);((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(search.getWindowToken(),0);save();}});addressEditor.addView(saveAddress,spaced(10));
        hero=row();hero.setPadding(dp(14),dp(16),dp(14),dp(16));hero.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,18));
        heroIcon=PowerStyle.icon(this,R.drawable.power_bolt,0xffffffff);heroIcon.setPadding(dp(12),dp(12),dp(12),dp(12));heroIcon.setBackground(PowerStyle.shape(this,PowerStyle.MUTED,40));hero.addView(heroIcon,new LinearLayout.LayoutParams(dp(58),dp(58)));
        LinearLayout heroCopy=column();LinearLayout.LayoutParams hc=new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1);hc.setMarginStart(dp(14));hero.addView(heroCopy,hc);
        heroTitle=PowerStyle.label(this,"Выберите свой адрес",19,PowerStyle.INK,true);heroCopy.addView(heroTitle);
        heroDetail=PowerStyle.label(this,"График появится после выбора группы",13,PowerStyle.MUTED,false);heroCopy.addView(heroDetail,spaced(6));
        heroTime=PowerStyle.label(this,"",19,PowerStyle.INK,true);heroCopy.addView(heroTime,spaced(3));heroTime.setVisibility(View.GONE);body.addView(hero,spaced(14));
        LinearLayout dates=row();dates.setPadding(dp(2),dp(2),dp(2),dp(2));dates.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,14));
        todayTab=PowerStyle.button(this,"Сегодня",true);tomorrowTab=PowerStyle.button(this,"Завтра",false);
        dates.addView(todayTab,new LinearLayout.LayoutParams(0,dp(48),1));dates.addView(tomorrowTab,new LinearLayout.LayoutParams(0,dp(48),1));
        todayTab.setOnClickListener(v->load(false));tomorrowTab.setOnClickListener(v->load(true));body.addView(dates,spaced(16));
        scheduleRows=column();body.addView(scheduleRows,spaced(8));
        Button refresh=PowerStyle.button(this,"Обновить",true);refresh.setCompoundDrawablesRelativeWithIntrinsicBounds(R.drawable.widget_refresh_dark,0,0,0);refresh.setCompoundDrawablePadding(dp(8));refresh.setOnClickListener(v->load(showingTomorrow));body.addView(refresh,spaced(10));
        updatedLabel=PowerStyle.label(this,"",11,PowerStyle.MUTED,false);updatedLabel.setGravity(android.view.Gravity.CENTER);body.addView(updatedLabel,spaced(8));
        status=PowerStyle.label(this,"Выберите населённый пункт из поиска и свою группу.",12,PowerStyle.MUTED,false);status.setGravity(android.view.Gravity.CENTER);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);body.addView(status,spaced(6));
        graph=new TextView(this);graph.setVisibility(View.GONE);body.addView(graph);
        status.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){if(addressEditor.getVisibility()==View.VISIBLE)addressHint.setText(s.length()==0?"Выберите населённый пункт из результатов поиска.":s);}public void afterTextChanged(Editable e){}});
        divider();
        LinearLayout settingsHeading=row(),settingsCopy=column();settingsCopy.addView(PowerStyle.label(this,widgetId==AppWidgetManager.INVALID_APPWIDGET_ID?"Настроить виджет":"Оформление виджета",17,PowerStyle.INK,true));
        settingsCopy.addView(PowerStyle.label(this,"Быстрый просмотр графика\nна главном экране",12,PowerStyle.MUTED,false),spaced(6));settingsHeading.addView(settingsCopy,new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1));
        previewHost=column();LinearLayout.LayoutParams previewParams=new LinearLayout.LayoutParams(dp(145),dp(88));previewParams.setMarginStart(dp(8));settingsHeading.addView(previewHost,previewParams);body.addView(settingsHeading);
        widgetTheme=new Spinner(this);widgetTheme.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"По теме устройства","Светлая","Тёмная OLED"}));widgetTheme.setVisibility(View.GONE);body.addView(widgetTheme);
        LinearLayout themes=row();themes.setPadding(dp(2),dp(2),dp(2),dp(2));themes.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,12));
        String[] names={"Светлая","OLED","Системная"};int[] indices={1,2,0};
        for(int i=0;i<3;i++){final int index=indices[i];Button b=PowerStyle.button(this,names[i],false);b.setTextSize(12);b.setPadding(dp(4),0,dp(4),0);themeTabs[i]=b;themes.addView(b,new LinearLayout.LayoutParams(0,dp(42),1));b.setOnClickListener(v->{widgetTheme.setSelection(index);updateThemeButtons();updateWidgetPreview();});}body.addView(themes,spaced(12));
        transparencyLabel=PowerStyle.label(this,"Прозрачность фона: 0%",13,PowerStyle.MUTED,false);body.addView(transparencyLabel,spaced(14));
        widgetTransparency=new SeekBar(this);widgetTransparency.setMax(100);widgetTransparency.setProgressTintList(android.content.res.ColorStateList.valueOf(PowerStyle.GREEN));widgetTransparency.setThumbTintList(android.content.res.ColorStateList.valueOf(PowerStyle.GREEN));body.addView(widgetTransparency,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(40)));
        widgetTransparency.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar bar,int value,boolean user){transparencyLabel.setText("Прозрачность фона: "+value+"%");if(user)updateWidgetPreview();}public void onStartTrackingTouch(SeekBar bar){}public void onStopTrackingTouch(SeekBar bar){}});
        TextView help=PowerStyle.label(this,"0% — сплошной фон, 100% — без фона. Текст остаётся непрозрачным. OLED — чёрная подложка.",11,PowerStyle.MUTED,false);body.addView(help);
        Button apply=PowerStyle.button(this,"Применить оформление",false);apply.setOnClickListener(v->{saveAppearance();if(widgetId!=AppWidgetManager.INVALID_APPWIDGET_ID)PowerWidget.render(this,widgetId);else AdaptivePowerViews.publishPreview(this);status.setText("Оформление сохранено.");Toast.makeText(this,"Оформление сохранено",Toast.LENGTH_SHORT).show();});body.addView(apply,spaced(12));
        if(widgetId==AppWidgetManager.INVALID_APPWIDGET_ID){Button add=PowerStyle.button(this,"Добавить виджет",false);add.setOnClickListener(v->pin(PowerWidget.class));body.addView(add,spaced(8));}
        Button source=PowerStyle.button(this,"Источник: Без Світла",false);source.setBackgroundColor(android.graphics.Color.TRANSPARENT);source.setOnClickListener(v->startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse("https://bezsvitla.com.ua"+selectedPath))));body.addView(source,spaced(12));
    }
    private LinearLayout column(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l;}
    private LinearLayout row(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.HORIZONTAL);l.setGravity(android.view.Gravity.CENTER_VERTICAL);return l;}
    private LinearLayout.LayoutParams spaced(int top){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);p.topMargin=dp(top);return p;}
    private void divider(){View line=new View(this);line.setBackgroundColor(0xffe3e3df);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(1));p.setMargins(0,dp(18),0,dp(18));body.addView(line,p);}
    private void updateAddress(){String group=groups.getSelectedItemPosition()>0?groupValues[groups.getSelectedItemPosition()]:"выберите группу";addressLabel.setText(selectedName.isEmpty()?"Выберите населённый пункт":selectedName.split(",")[0]+" · Группа "+group);}
    private void updateThemeButtons(){int[] index={1,2,0};for(int i=0;i<3;i++){boolean selected=widgetTheme.getSelectedItemPosition()==index[i];PowerStyle.clickable(this,themeTabs[i],selected?PowerStyle.ON:PowerStyle.NEUTRAL,10);themeTabs[i].setTextColor(selected?PowerStyle.GREEN:PowerStyle.MUTED);themeTabs[i].setSelected(selected);}}
    private void updateWidgetPreview(){
        if(previewHost==null||widgetTransparency==null)return;
        SharedPreferences preview=getSharedPreferences("power_appearance_preview",MODE_PRIVATE);
        preview.edit().putString("name",selectedName.isEmpty()?"Ваш город":selectedName).putString("group",groups.getSelectedItemPosition()>0?groupValues[groups.getSelectedItemPosition()]:"—").putString("widget_theme",new String[]{"system","light","dark"}[widgetTheme.getSelectedItemPosition()]).putString("widget_transparency",Integer.toString(widgetTransparency.getProgress())).apply();
        previewHost.removeAllViews();
        SharedPreferences saved=PowerData.prefs(this,dataId());boolean matches=!selectedPath.isEmpty()&&selectedPath.equals(saved.getString("path",""))&&groupValues[groups.getSelectedItemPosition()].equals(saved.getString("group",""));
        previewHost.addView(AdaptivePowerViews.make(this,0,preview,matches?PowerData.cached(this,dataId(),false):new JSONObject(),matches?PowerData.cached(this,dataId(),true):new JSONObject(),screenNow(),145,88).apply(this,previewHost),new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        previewHost.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
    }
    private void clearSchedule(){graph.setText("");scheduleRows.removeAllViews();emptySchedule("График не загружен","Выберите адрес и группу");updateWidgetPreview();}
    private void loadGroups(){
        final String path=selectedPath;final int token=request;
        String keep=groups.getSelectedItemPosition()>0?groupValues[groups.getSelectedItemPosition()]:"";
        worker.execute(()->{
            try {
                JSONObject data=PowerData.get(PowerData.server(this)+"/power/options?location="+PowerData.encode(path));
                JSONArray list=data.getJSONArray("groups");java.util.ArrayList<String> values=new java.util.ArrayList<>();values.add("Выберите группу");
                for(int i=0;i<list.length();i++)values.add(list.optString(i));
                if(!keep.isEmpty()&&!values.contains(keep))values.add(keep);
                main.post(()->{if(token!=request||isFinishing()||!path.equals(selectedPath))return;
                    groupValues=values.toArray(new String[0]);int position=keep.isEmpty()?0:values.indexOf(keep);
                    observedGroup=groupValues[position];groups.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,groupValues));groups.setSelection(position);
                    if(!data.optBoolean("available")&&keep.isEmpty()){status.setText("Сегодня без графиков");emptySchedule("Сегодня без графиков","Источник ещё не опубликовал расписание.");}
                });
            } catch(Exception ignored) {main.post(()->{if(token==request&&!isFinishing())status.setText("Не удалось загрузить группы. Можно выбрать известную группу вручную или повторить обновление.");});}
        });
    }
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private void pin(Class<?> provider){
        if(!valid())return;savePreferences();
        AppWidgetManager manager=AppWidgetManager.getInstance(this);
        if(manager.isRequestPinAppWidgetSupported()){
            android.os.Bundle preview=new android.os.Bundle();
            preview.putParcelable(AppWidgetManager.EXTRA_APPWIDGET_PREVIEW,AdaptivePowerViews.preview(this));
            manager.requestPinAppWidget(new ComponentName(this,provider),preview,null);
        }
        else status.setText("Удерживайте свободное место на главном экране → Виджеты → Abstergo.");
    }
    private TextView text(String s,int size){TextView v=new TextView(this);v.setText(s);v.setTextSize(size);v.setTextColor(0xff32291f);v.setPadding(0,dp(10),0,dp(10));body.addView(v);return v;}
    private void button(String title,Runnable action){Button b=new Button(this);b.setText(title);b.setOnClickListener(v->action.run());body.addView(b,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));}
    private boolean valid(){if(selectedPath.isEmpty()||groups.getSelectedItemPosition()==0){status.setText("Сначала выберите населённый пункт из поиска и группу.");return false;}return true;}
    protected int dataId(){return widgetId==AppWidgetManager.INVALID_APPWIDGET_ID?0:widgetId;}
    protected boolean isDesignPreview(){return false;}
    protected java.time.ZonedDateTime screenNow(){return java.time.ZonedDateTime.now(PowerData.KYIV);}
    private void saveAppearance(){
        String theme=new String[]{"system","light","dark"}[widgetTheme.getSelectedItemPosition()];
        PowerData.prefs(this,dataId()).edit().putString("widget_theme",theme).putString("widget_transparency",Integer.toString(widgetTransparency.getProgress())).apply();
    }
    private void savePreferences(){
        saveAppearance();
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
        if(!valid())return;savePreferences();updateAddress();final int id=dataId();final int token=++request;
        display(PowerData.cached(this,id,tomorrow),tomorrow,true);status.setText("Обновляю график…");
        worker.execute(()->{
            try {JSONObject data=PowerData.fetch(this,id,tomorrow);main.post(()->{if(token==request&&!isFinishing()){display(data,tomorrow,data.optBoolean("stale"));status.setText(data.optBoolean("stale")?"Источник недоступен · сохранённые данные":data.optBoolean("published")?"График обновлён":(tomorrow?"Завтра":"Сегодня")+" без графиков");}});}
            catch(Exception e){main.post(()->{if(token==request&&!isFinishing())status.setText("Нет соединения с графиками. Показаны сохранённые данные, если они есть.");});}
        });
    }
    protected void display(JSONObject data,boolean tomorrow,boolean cached){
        status.setText(cached?"Сохранённый график · обновляю данные":"");
        showingTomorrow=tomorrow;scheduleRows.removeAllViews();
        java.time.ZonedDateTime now=screenNow();
        java.time.LocalDate date=now.toLocalDate().plusDays(tomorrow?1:0);
        String expected=date.toString();
        java.time.format.DateTimeFormatter shortDate=java.time.format.DateTimeFormatter.ofPattern("d MMM",new java.util.Locale("ru"));
        todayTab.setText("Сегодня\n"+now.toLocalDate().format(shortDate));
        tomorrowTab.setText("Завтра\n"+now.toLocalDate().plusDays(1).format(shortDate));
        for(Button b:new Button[]{todayTab,tomorrowTab}){boolean active=b==(tomorrow?tomorrowTab:todayTab);PowerStyle.clickable(this,b,active?PowerStyle.GREEN:PowerStyle.NEUTRAL,12);b.setTextColor(active?0xffffffff:PowerStyle.MUTED);b.setTextSize(13);}
        heroTime.setVisibility(View.GONE);
        if(!expected.equals(data.optString("date"))){
            emptySchedule("График не загружен","Проверьте соединение и нажмите «Обновить».");return;
        }
        if(!data.optBoolean("published")){
            emptySchedule((tomorrow?"Завтра":"Сегодня")+" без графиков","Источник ещё не опубликовал расписание.");return;
        }
        JSONArray slots=data.optJSONArray("intervals");
        int minute=now.getHour()*60+now.getMinute();String current="";
        if(!tomorrow&&slots!=null)for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s!=null&&s.optInt("start")<=minute&&minute<s.optInt("end"))current=s.optString("status");}
        String state=tomorrow?"":current;boolean on="on".equals(state),off="off".equals(state);
        hero.setBackground(PowerStyle.shape(this,on?PowerStyle.ON:off?PowerStyle.OFF:PowerStyle.NEUTRAL,18));
        heroTitle.setText(tomorrow?"График на завтра":on?"По графику свет есть":off?"По графику нет света":"Статус уточняется");
        heroTitle.setTextColor(on?PowerStyle.GREEN:off?PowerStyle.RED:PowerStyle.INK);
        heroIcon.setBackground(PowerStyle.shape(this,on?PowerStyle.GREEN:off?PowerStyle.RED:PowerStyle.MUTED,40));
        JSONObject next=null;
        if(slots!=null)for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s!=null&&(tomorrow||s.optInt("start")>minute)&&"off".equals(s.optString("status"))){next=s;break;}}
        if(off&&!tomorrow&&slots!=null){next=null;for(int i=0;i<slots.length();i++){JSONObject s=slots.optJSONObject(i);if(s!=null&&s.optInt("start")>minute&&"on".equals(s.optString("status"))){next=s;break;}}heroDetail.setText(next==null?"По графику до конца дня":"Следующее включение");}
        else heroDetail.setText(next==null?"По опубликованному графику":"Следующее отключение");
        if(next!=null){heroTime.setText(off&&!tomorrow?PowerData.clock(next.optInt("start")):PowerData.clock(next.optInt("start"))+" – "+PowerData.clock(next.optInt("end")));heroTime.setVisibility(View.VISIBLE);}
        else if(on){heroDetail.setText("Без новых отключений до конца дня");}
        if(slots!=null)for(int i=0;i<slots.length();i++){
            JSONObject s=slots.optJSONObject(i);if(s==null)continue;
            String code=s.optString("status");boolean light="on".equals(code),outage="off".equals(code);
            LinearLayout line=row();line.setPadding(dp(14),dp(10),dp(14),dp(10));
            line.setBackground(PowerStyle.shape(this,light?PowerStyle.ON:outage?PowerStyle.OFF:PowerStyle.NEUTRAL,12));
            boolean past=!tomorrow&&s.optInt("end")<=minute,active=!tomorrow&&s.optInt("start")<=minute&&minute<s.optInt("end");
            TextView range=PowerStyle.label(this,PowerData.clock(s.optInt("start"))+" – "+PowerData.clock(s.optInt("end")),14,past?PowerStyle.MUTED:PowerStyle.INK,active);
            line.addView(range,new LinearLayout.LayoutParams(0,ViewGroup.LayoutParams.WRAP_CONTENT,1));
            ImageView glyph=PowerStyle.icon(this,light?R.drawable.widget_lightbulb:outage?R.drawable.widget_bulb_off:R.drawable.widget_flash_on,light?PowerStyle.GREEN:outage?PowerStyle.RED:PowerStyle.MUTED);
            line.addView(glyph,new LinearLayout.LayoutParams(dp(16),dp(16)));
            TextView label=PowerStyle.label(this,light?"Свет есть":outage?"Без света":"Уточняется",13,light?PowerStyle.GREEN:outage?PowerStyle.RED:PowerStyle.MUTED,false);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,ViewGroup.LayoutParams.WRAP_CONTENT);lp.setMarginStart(dp(6));line.addView(label,lp);
            line.setContentDescription(range.getText()+" · "+label.getText()+(active?" · сейчас":""));scheduleRows.addView(line,spaced(5));
        }
        if(slots==null||slots.length()==0){emptySchedule("Нет точных данных","Источник не указал интервалы.");return;}
        updatedLabel.setText("Обновлено: "+data.optString("sourceUpdated","время не указано")+(cached?" · сохранено":""));
        updateWidgetPreview();
    }
    private void emptySchedule(String title,String detail){
        heroTitle.setText(title);heroTitle.setTextColor(PowerStyle.INK);heroDetail.setText(detail);heroTime.setVisibility(View.GONE);
        hero.setBackground(PowerStyle.shape(this,PowerStyle.NEUTRAL,18));heroIcon.setBackground(PowerStyle.shape(this,PowerStyle.MUTED,40));updatedLabel.setText("");
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);recreate();}
    @Override protected void onDestroy(){request++;if(searchTask!=null)main.removeCallbacks(searchTask);worker.shutdownNow();super.onDestroy();}
}
