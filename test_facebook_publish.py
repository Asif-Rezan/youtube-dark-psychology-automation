import copy
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from facebook_publish import Facebook, FacebookError, PAGE_ID, publish, finish_fields, schedule_timestamp, verify_remote


class FacebookPublishingTests(unittest.TestCase):
    def test_schedule_bounds_and_disclosure(self):
        now = dt.datetime(2026,10,30,tzinfo=dt.timezone.utc)
        for seconds in (0,600,29*86400,30*86400):
            with self.assertRaises(FacebookError):
                schedule_timestamp((now+dt.timedelta(seconds=seconds)).isoformat(),now)
        self.assertEqual(schedule_timestamp((now+dt.timedelta(days=4)).isoformat(),now),int(now.timestamp())+4*86400)
        meta={'title':'Song','description':'Created with AI'}
        short=finish_fields('short','1','',meta,123)
        self.assertEqual(short['video_state'],'SCHEDULED')
        self.assertEqual(short['is_ai_generated'],'true')
        long=finish_fields('video','1','2',meta,123)
        self.assertEqual(long['published'],'false')
        self.assertEqual(long['scheduled_publish_time'],short['scheduled_publish_time'])

    def test_page_token_and_untrusted_hosts_are_rejected(self):
        session=Mock()
        session.request.return_value=Mock(status_code=200,json=lambda:{'id':'wrong'})
        api=Facebook('private-token',session)
        with self.assertRaises(FacebookError): api.verify_page()
        session.request.reset_mock()
        with self.assertRaises(FacebookError): api.request('POST','/upload',host='attacker.example')
        with self.assertRaises(FacebookError): api.request('POST','//attacker.example/upload')
        session.request.assert_not_called()
        session.request.return_value=Mock(status_code=400,json=lambda:{'error':{'code':190,'message':'private-token'}})
        with self.assertRaises(FacebookError) as raised: api.request('GET','/me')
        self.assertNotIn('private-token',str(raised.exception))

    def test_remote_identity_schedule_and_processing_guards(self):
        state={'video_id':'123','publish_at':1234}
        remote={'id':'123','from':{'id':PAGE_ID},'scheduled_publish_time':1234,'status':{'video_status':'ready'}}
        self.assertTrue(verify_remote(remote,state))
        for field,value in [('id','other'),('from',{'id':'other'}),('scheduled_publish_time',1235),('status',{'video_status':'error'})]:
            bad=copy.deepcopy(remote);bad[field]=value
            with self.assertRaises(FacebookError): verify_remote(bad,state)
        del remote['scheduled_publish_time']
        self.assertFalse(verify_remote(remote,state))

    def test_retries_reuse_existing_video_and_never_publish_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'video.mp4';path.write_bytes(b'video-bytes')
            api=Mock();api.status.return_value={'id':'123','from':{'id':PAGE_ID},'scheduled_publish_time':1234,
                'status':{'video_status':'ready','uploading_phase':{'status':'complete'}}}
            api.request.side_effect=[{'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v26.0/123'}, {'success':True}]
            state={};save=Mock()
            publish(api,path,'short',{'title':'Song','description':'AI'},1234,state,save,sleep=lambda _:None)
            self.assertEqual(state['phase'],'scheduled')
            self.assertEqual(api.request.call_count,2)
            api.request.reset_mock()
            publish(api,path,'short',{'title':'Song','description':'AI'},1234,state,save,sleep=lambda _:None)
            api.request.assert_not_called()
            with self.assertRaises(FacebookError):
                publish(api,path,'short',{'title':'Changed','description':'AI'},1234,state,save)

    def test_lost_initialization_response_stops_duplicate_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'video.mp4';path.write_bytes(b'video-bytes')
            api=Mock();api.request.side_effect=FacebookError('transport failed')
            state={};save=Mock()
            for _ in range(2):
                with self.assertRaises(FacebookError):
                    publish(api,path,'video',{'title':'Song','description':'AI'},1234,state,save)
            self.assertEqual(api.request.call_count,1)

    def test_long_chunks_resume_with_one_video_and_finish(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'video.mp4';path.write_bytes(b'abcdefgh')
            api=Mock();api.request.side_effect=[{'video_id':'123','upload_session_id':'456','start_offset':'0','end_offset':'4'},
                {'start_offset':'4','end_offset':'8'},{'start_offset':'8','end_offset':'8'},{'success':True}]
            api.status.return_value={'id':'123','from':{'id':PAGE_ID},'scheduled_publish_time':1234,'status':{'video_status':'ready'}}
            state={}
            publish(api,path,'video',{'title':'Song','description':'AI'},1234,state,Mock(),sleep=lambda _:None)
            self.assertEqual(state['phase'],'scheduled')
            self.assertEqual(api.request.call_args_list[1].kwargs['files']['video_file_chunk'][1],b'abcd')
            self.assertEqual(api.request.call_args_list[2].kwargs['files']['video_file_chunk'][1],b'efgh')
            self.assertEqual(api.request.call_args_list[-1].kwargs['data']['upload_session_id'],'456')
