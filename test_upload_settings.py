import copy
import datetime as dt
import os
import unittest
from unittest.mock import patch, Mock
from upload_settings import load_settings, upload_body, verified_phase, new_york_publish_time, schedule_uploaded_video

class UploadSettingsTests(unittest.TestCase):
    def test_public_and_disclosures(self):
        with patch.dict(os.environ,{'UPLOAD_MODE':'public'},clear=True):
            settings=load_settings()
        body=upload_body({'title':'Dudi'},'Description',['kids'],settings)
        self.assertEqual(body['status']['privacyStatus'],'public')
        self.assertTrue(body['status']['selfDeclaredMadeForKids'])
        self.assertTrue(body['status']['containsSyntheticMedia'])
        self.assertEqual(body['snippet']['categoryId'],'10')
        self.assertNotIn('publishAt',body['status'])

    def test_schedule_and_timezone(self):
        with patch.dict(os.environ,{'UPLOAD_MODE':'scheduled','PUBLISH_AT':'2030-01-01T18:00:00+06:00'},clear=True):
            settings=load_settings(now=dt.datetime(2026,1,1,tzinfo=dt.timezone.utc))
        body=upload_body({'title':'Dudi'},'Description',[],settings)
        self.assertEqual(body['status']['privacyStatus'],'private')
        self.assertEqual(body['status']['publishAt'],'2030-01-01T12:00:00Z')

    def test_reject_bad_schedule(self):
        for value in ('2020-01-01T00:00:00Z','2030-01-01T18:00:00'):
            with patch.dict(os.environ,{'UPLOAD_MODE':'scheduled','PUBLISH_AT':value},clear=True),self.assertRaises(ValueError):
                load_settings()

    def test_verify_public_and_scheduled_and_mismatches(self):
        for mode in ('public','scheduled'):
            env={'UPLOAD_MODE':mode}
            if mode=='scheduled': env['PUBLISH_AT']='2030-01-01T12:00:00Z'
            with patch.dict(os.environ,env,clear=True): settings=load_settings()
            body=upload_body({'title':'Dudi'},'Description',['kids'],settings)
            video=copy.deepcopy(body)
            video['snippet']['channelId']='right-channel'
            video['status']['uploadStatus']='processed'
            video['processingDetails']={'processingStatus':'succeeded'}
            video['contentDetails']={'definition':'hd'}
            self.assertEqual(verified_phase(video,body,'right-channel'),'published' if mode=='public' else 'scheduled')
            with self.assertRaises(RuntimeError): verified_phase(video,body,'wrong-channel')
            video['status']['containsSyntheticMedia']=False
            with self.assertRaises(RuntimeError): verified_phase(video,body,'right-channel')

    def test_scheduled_video_can_become_public(self):
        with patch.dict(os.environ,{'UPLOAD_MODE':'scheduled','PUBLISH_AT':'2030-01-01T12:00:00Z'},clear=True): settings=load_settings()
        body=upload_body({'title':'Dudi'},'Description',[],settings)
        video=copy.deepcopy(body)
        video['snippet']['channelId']='channel'
        video['status'].update(privacyStatus='public',uploadStatus='processed')
        video['status'].pop('publishAt')
        video['processingDetails']={'processingStatus':'succeeded'}
        video['contentDetails']={'definition':'hd'}
        self.assertEqual(verified_phase(video,body,'channel'),'published')

    def test_automatic_schedule_is_default_and_initial_upload_is_private(self):
        with patch.dict(os.environ,{},clear=True):
            settings=load_settings()
        self.assertEqual(settings['mode'],'scheduled')
        self.assertIsNone(settings['publish_at'])
        body=upload_body({'title':'Dudi'},'description',[],settings)
        self.assertEqual(body['status']['privacyStatus'],'private')
        self.assertNotIn('publishAt',body['status'])

    def test_new_york_time_boundaries_and_daylight_saving(self):
        from zoneinfo import ZoneInfo
        for finished, expected in [
            ('2026-10-28T08:00:00Z','2026-10-31T10:00:00Z'),
            ('2026-10-28T10:00:00Z','2026-10-31T10:00:00Z'),
            ('2026-10-28T10:00:01Z','2026-11-01T11:00:00Z'),
            ('2026-10-30T10:30:00Z','2026-11-02T11:00:00Z'),
            ('2027-03-12T10:30:00Z','2027-03-16T10:00:00Z'),
            ('2027-01-05T20:00:00Z','2027-01-09T11:00:00Z')]:
            end=dt.datetime.fromisoformat(finished.replace('Z','+00:00'))
            result=new_york_publish_time(end)
            self.assertEqual(result,expected)
            when=dt.datetime.fromisoformat(result.replace('Z','+00:00'))
            self.assertGreaterEqual((when-end).total_seconds(),72*3600)
            self.assertEqual(when.astimezone(ZoneInfo('America/New_York')).hour,6)

    def test_schedule_after_upload_freezes_target_across_update_retry(self):
        with patch.dict(os.environ,{},clear=True): settings=load_settings()
        state={'video_id':'video','upload_settings':settings,
            'upload_completed_at':'2026-10-28T12:00:00Z',
            'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
        client,save=Mock(),Mock()
        live={'id':'video','snippet':{},'status':{'privacyStatus':'private','uploadStatus':'processed'},
              'processingDetails':{'processingStatus':'succeeded'}}
        client.videos().list().execute.side_effect=lambda **kwargs: {'items':[copy.deepcopy(live)]}
        calls=[]
        def update(**kwargs):
            calls.append(True)
            if len(calls)==1:
                raise RuntimeError('interrupted')
            live['status']['publishAt']=state['schedule_target']
            return {}
        client.videos().update().execute.side_effect=update
        now=dt.datetime(2026,10,28,12,tzinfo=dt.timezone.utc)
        with self.assertRaises(RuntimeError): schedule_uploaded_video(client,state,save,now)
        self.assertFalse(state.get('schedule_configured',False))
        target=state['schedule_target']
        with patch('upload_settings.time.sleep'):
            schedule_uploaded_video(client,state,save,now+dt.timedelta(hours=2))
        self.assertEqual(state['schedule_target'],target)
        self.assertTrue(state['schedule_configured'])
        call=client.videos().update.call_args.kwargs
        self.assertEqual(call['body']['status']['publishAt'],target)
        self.assertEqual(call['body']['status']['privacyStatus'],'private')
        count=client.videos().update.call_count
        schedule_uploaded_video(client,state,save,now+dt.timedelta(hours=3))
        self.assertEqual(client.videos().update.call_count,count)

    def test_missing_ai_field_requires_bound_write_receipt_and_false_never_passes(self):
        with patch.dict(os.environ,{'UPLOAD_MODE':'public'},clear=True): settings=load_settings()
        body=upload_body({'title':'Dudi'},'Description',[],settings)
        video=copy.deepcopy(body)
        video.update(id='video',processingDetails={'processingStatus':'succeeded'},contentDetails={'definition':'hd'})
        video['snippet']['channelId']='channel'
        video['status']['uploadStatus']='processed'
        del video['status']['containsSyntheticMedia']
        with self.assertRaises(RuntimeError): verified_phase(video,body,'channel')
        receipt={'video_id':'video','accepted':True}
        self.assertEqual(verified_phase(video,body,'channel',receipt),'published')
        with self.assertRaises(RuntimeError): verified_phase(video,body,'channel',dict(receipt,video_id='other'))
        video['status']['containsSyntheticMedia']=False
        with self.assertRaises(RuntimeError): verified_phase(video,body,'channel',receipt)

    def test_disclosure_repair_preserves_live_schedule_and_records_acceptance(self):
        from upload_settings import ensure_synthetic_disclosure
        state={'video_id':'video','upload_body':{'status':{'containsSyntheticMedia':True}}}
        video={'id':'video','status':{'privacyStatus':'private','publishAt':'2030-01-01T12:00:00Z',
            'selfDeclaredMadeForKids':True,'license':'youtube','embeddable':True,'publicStatsViewable':True}}
        client,save=Mock(),Mock()
        client.videos().update().execute.return_value=copy.deepcopy(video)
        ensure_synthetic_disclosure(client,video,state,save)
        sent=client.videos().update.call_args.kwargs['body']
        self.assertEqual(sent['status'],dict(video['status'],containsSyntheticMedia=True))
        self.assertTrue(state['synthetic_disclosure_receipt']['accepted'])
        save.assert_called_once()
        count=client.videos().update.call_count
        ensure_synthetic_disclosure(client,video,state,save)
        self.assertEqual(count,client.videos().update.call_count)

    def test_failed_disclosure_update_does_not_record_receipt(self):
        from upload_settings import ensure_synthetic_disclosure
        for response in ({'id':'other'}, {'id':'video','status':{'containsSyntheticMedia':False}}):
            state={'video_id':'video','upload_body':{'status':{'containsSyntheticMedia':True}}}
            client,save=Mock(),Mock()
            client.videos().update().execute.return_value=response
            with self.assertRaises(RuntimeError):
                ensure_synthetic_disclosure(client,{'id':'video','status':{'privacyStatus':'private'}},state,save)
            self.assertNotIn('synthetic_disclosure_receipt',state)
            save.assert_not_called()

    def test_schedule_waits_for_processing_then_recovers_recent_owned_403(self):
        from googleapiclient.errors import HttpError
        import httplib2
        with patch.dict(os.environ, {'EXPECTED_CHANNEL_ID':'channel'},clear=True):
            settings=load_settings()
            state={'video_id':'video','upload_settings':settings,
                'upload_completed_at':'2026-10-29T12:00:00Z',
                'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
            client,save=Mock(),Mock()
            live={'id':'video','snippet':{'channelId':'channel'},
                'status':{'privacyStatus':'private','uploadStatus':'processed'},
                'processingDetails':{'processingStatus':'succeeded'}}
            processing=copy.deepcopy(live)
            processing['status']['uploadStatus']='uploaded'
            processing['processingDetails']['processingStatus']='processing'
            reads=[]
            def read(**kwargs):
                reads.append(True)
                return {'items':[copy.deepcopy(processing if len(reads)==1 else live)]}
            client.videos().list().execute.side_effect=read
            error=HttpError(httplib2.Response({'status':'403'}),
                b'{"error":{"errors":[{"reason":"forbidden"}]}}')
            writes=[]
            def write(**kwargs):
                writes.append(True)
                if len(writes)==1: raise error
                live['status']['publishAt']=state['schedule_target']
                return {}
            client.videos().update().execute.side_effect=write
            with patch('upload_settings.time.sleep'):
                schedule_uploaded_video(client,state,save,dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc))
            self.assertTrue(state['schedule_configured'])
            self.assertEqual(len(writes),2)
            self.assertFalse(state.get('schedule_pending'))

    def test_schedule_reconciles_already_applied_time_without_update(self):
        settings=load_settings()
        state={'video_id':'video','upload_settings':settings,
            'upload_completed_at':'2026-10-29T12:00:00Z',
            'schedule_target':'2026-11-02T11:00:00Z',
            'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
        client=Mock()
        client.videos.return_value.list.return_value.execute.return_value={'items':[
            {'id':'video','status':{'privacyStatus':'private','publishAt':state['schedule_target']}}]}
        schedule_uploaded_video(client,state,Mock(),dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc))
        self.assertTrue(state['schedule_configured'])
        client.videos.return_value.update.assert_not_called()

    def test_schedule_quota_denial_is_not_blindly_retried(self):
        from googleapiclient.errors import HttpError
        import httplib2
        settings=load_settings()
        state={'video_id':'video','upload_settings':settings,
            'upload_completed_at':'2026-10-29T12:00:00Z',
            'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
        client=Mock()
        client.videos.return_value.list.return_value.execute.return_value={'items':[
            {'id':'video','status':{'privacyStatus':'private','uploadStatus':'processed'}}]}
        client.videos.return_value.update.return_value.execute.side_effect=HttpError(
            httplib2.Response({'status':'403'}),b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
        with patch('upload_settings.time.sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError,'permission or quota denied'):
                schedule_uploaded_video(client,state,Mock(),dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc))
        sleep.assert_not_called()
        self.assertFalse(state.get('schedule_configured',False))
        self.assertEqual(state['video_id'],'video')
        client.videos.return_value.insert.assert_not_called()

    def test_processing_wait_is_bounded_and_preserves_pending_checkpoint(self):
        settings=load_settings()
        state={'video_id':'video','upload_settings':settings,
            'upload_completed_at':'2026-10-29T12:00:00Z',
            'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
        client=Mock()
        client.videos.return_value.list.return_value.execute.return_value={'items':[
            {'id':'video','status':{'privacyStatus':'private','uploadStatus':'uploaded'},
             'processingDetails':{'processingStatus':'processing'}}]}
        with patch('upload_settings.time.sleep'):
            with self.assertRaises(TimeoutError):
                schedule_uploaded_video(client,state,Mock(),dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc))
        self.assertEqual(client.videos.return_value.list.call_count,90)
        self.assertTrue(state['schedule_pending'])
        client.videos.return_value.update.assert_not_called()

    def test_processing_longer_than_old_two_minute_window_schedules_same_video(self):
        with patch.dict(os.environ, {'EXPECTED_CHANNEL_ID':'channel'}, clear=True):
            settings=load_settings()
            state={'video_id':'existing-short','upload_settings':settings,
                'upload_completed_at':'2026-10-29T12:00:00Z',
                'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
            client,save=Mock(),Mock()
            processing={'id':'existing-short','snippet':{'channelId':'channel'},
                'status':{'privacyStatus':'private','uploadStatus':'uploaded'},
                'processingDetails':{'processingStatus':'processing'}}
            ready=copy.deepcopy(processing)
            ready['status']['uploadStatus']='processed'
            ready['processingDetails']['processingStatus']='succeeded'
            reads=[]
            def read(**kwargs):
                reads.append(True)
                result=copy.deepcopy(processing if len(reads)<=15 else ready)
                if len(reads)>16:
                    result['status']['publishAt']=state['schedule_target']
                return {'items':[result]}
            client.videos().list().execute.side_effect=read
            with patch('upload_settings.time.sleep') as sleep:
                schedule_uploaded_video(client,state,save,dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc))
            self.assertTrue(state['schedule_configured'])
            self.assertEqual(state['video_id'],'existing-short')
            self.assertEqual(state['schedule_target'],new_york_publish_time(dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc)))
            client.videos().insert.assert_not_called()
            client.videos().update.assert_called_once()
            self.assertGreaterEqual(sleep.call_count,15)

    def test_schedule_obeys_shared_deadline_and_keeps_same_id_for_recovery(self):
        settings=load_settings()
        state={'video_id':'existing-short','upload_settings':settings,
            'upload_completed_at':'2026-10-29T12:00:00Z',
            'upload_body':upload_body({'title':'Dudi'},'description',[],settings)}
        client,save=Mock(),Mock()
        client.videos().list().execute.return_value={'items':[
            {'id':'existing-short','status':{'privacyStatus':'private','uploadStatus':'uploaded'},
             'processingDetails':{'processingStatus':'processing'}}]}
        with patch('upload_settings.time.monotonic',side_effect=[0,0,1,2,3]), patch('upload_settings.time.sleep'):
            with self.assertRaisesRegex(TimeoutError,'resume the existing video ID'):
                schedule_uploaded_video(client,state,save,dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc),deadline=3)
        self.assertTrue(state['schedule_pending'])
        self.assertEqual(state['video_id'],'existing-short')
        client.videos().insert.assert_not_called()
